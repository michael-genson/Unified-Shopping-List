import base64
import hashlib
import hmac
import logging
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Request

from .. import config
from ..app import services
from ..app_secrets import APP_CLIENT_ID, APP_CLIENT_SECRET, TODOIST_CLIENT_SECRET
from ..handlers.core import SQSSyncMessageHandler
from ..models.account_linking import NotLinkedError
from ..models.alexa import AlexaListEvent, AlexaSyncEvent
from ..models.aws import SQSEvent
from ..models.core import BaseSyncEvent, RateLimitCategory, User
from ..models.mealie import MealieEventNotification, MealieEventType, MealieSyncEvent
from ..models.todoist import TodoistEventType, TodoistSyncEvent, TodoistWebhook
from .auth import get_current_user

router = APIRouter(prefix="/api/handlers", tags=["Handlers"])


@router.post("/sqs/sync-events")
async def sqs_sync_event_handler(event: SQSEvent) -> None:
    """Process all sync events from SQS"""

    processed_event_sources: set[str] = set()
    for message in event.records:
        try:
            # make sure we can process this sync event
            sync_event = message.parse_body(BaseSyncEvent)
            if str(sync_event.source) in processed_event_sources:
                continue

            if sync_event.client_id != APP_CLIENT_ID or sync_event.client_secret != APP_CLIENT_SECRET:
                logging.error("Received sync event with invalid client id & secret pair, aborting")
                continue

            _user_in_db = services.user.get_user(sync_event.username)
            if not _user_in_db:
                logging.error(f"Cannot find sync event user {sync_event.username}, aborting")
                continue

            user = _user_in_db.cast(User)
            if not user.is_linked_to_mealie:
                raise NotLinkedError(user.username, "mealie")

            message_handler = SQSSyncMessageHandler(user)
            processed_event_source = message_handler.handle_message(message)
            if processed_event_source:
                processed_event_sources.add(str(processed_event_source))

        except Exception as e:
            # TODO: handle this in a DLQ and add support for partial-retries
            logging.error("Unhandled exception when trying to process a message from SQS")
            logging.error(f"{type(e).__name__}: {e}")
            logging.error(message)


@router.post("/mealie")
async def mealie_event_notification_handler(
    notification: MealieEventNotification, username: str, security_hash: Optional[str] = None
) -> None:
    if notification.event_type == MealieEventType.invalid:
        return

    if notification.integration_id == config.MEALIE_INTEGRATION_ID:
        return

    shopping_list_id = notification.get_shopping_list_id_from_document_data()
    if not shopping_list_id:
        return

    _user_in_db = services.user.get_user(username)
    if not _user_in_db:
        return

    user = _user_in_db.cast(User)
    if not user.configuration.mealie:
        return

    # confirm the origin of the notification using the security hash
    if security_hash != user.configuration.mealie.security_hash:
        return

    # check if the user configured this shopping list
    if shopping_list_id not in user.list_sync_maps:
        return

    # verify user rate limit; raises 429 error if the rate limit is violated
    services.rate_limit.verify_rate_limit(user, RateLimitCategory.sync)

    # initiate a sync event
    sync_event = MealieSyncEvent(
        event_id=notification.event_id,
        username=user.username,
        shopping_list_id=shopping_list_id,
        timestamp=notification.timestamp,
    )

    sync_event.send_to_queue(use_dev_route=user.use_developer_routes)


@router.post("/todoist")
async def todoist_event_notification_handler(request: Request, webhook: TodoistWebhook) -> None:
    if webhook.event_name == TodoistEventType.invalid:
        return

    project_id = webhook.event_data.get("project_id")
    if not project_id:
        return

    # verify Todoist security header
    # https://developer.todoist.com/sync/v9#request-format
    security_header = request.headers.get("X-Todoist-Hmac-SHA256")
    if not security_header:
        logging.error("Received Todoist webhook with missing security header")
        return

    hmac_signature = hmac.new(
        key=TODOIST_CLIENT_SECRET.encode("utf-8"),
        msg=await request.body(),
        digestmod=hashlib.sha256,
    )

    target_header = base64.b64encode(hmac_signature.digest()).decode()
    if security_header != target_header:
        logging.error("Received Todoist webhook with invalid security header")
        return

    # find all users linked to this Todoist account
    linked_usernames = services.user.get_usernames_by_secondary_index("todoist_user_id", webhook.user_id)

    users: list[User] = []
    for username in linked_usernames:
        _user_in_db = services.user.get_user(username)
        if not _user_in_db:
            continue

        user = _user_in_db.cast(User)

        if not (user.is_linked_to_mealie and user.is_linked_to_todoist):
            continue

        # check if the user configured this project
        subscribed_to_project = False

        for list_sync_map in user.list_sync_maps.values():
            if list_sync_map.todoist_project_id == project_id:
                subscribed_to_project = True
                break

        if not subscribed_to_project:
            return

        users.append(user)

    if not users:
        return

    # verify user rate limit; raises 429 error if the rate limit is violated
    services.rate_limit.verify_rate_limit(user, RateLimitCategory.sync)

    # initiate a sync event for each linked user (there should only be one)
    event_id_base = request.headers.get("X-Todoist-Delivery-ID") or str(uuid4())
    for user in users:
        sync_event = TodoistSyncEvent(
            event_id="|".join([user.username, event_id_base]),
            username=user.username,
            project_id=project_id,
        )

        sync_event.send_to_queue(use_dev_route=user.use_developer_routes)


@router.post("/alexa")
@services.rate_limit.limit(RateLimitCategory.sync)
async def alexa_event_notification_handler(event: AlexaListEvent, user: User = Depends(get_current_user)) -> None:
    sync_event = AlexaSyncEvent(
        event_id=event.request_id, username=user.username, list_event=event, timestamp=event.timestamp
    )

    sync_event.send_to_queue(use_dev_route=user.use_developer_routes)
