import base64
import hashlib
import hmac
import json
from datetime import datetime

from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient

from AppLambda.src.app import app, secrets, settings
from AppLambda.src.models.alexa import AlexaListEvent, ObjectType, Operation
from AppLambda.src.models.core import User
from AppLambda.src.models.mealie import MealieEventNotification, MealieEventType
from AppLambda.src.models.todoist import TodoistEventType, TodoistWebhook
from AppLambda.src.routes import event_handlers
from tests.utils.users import get_auth_headers

from .generators import random_string


def _get_api_client():
    return TestClient(app)


def build_mealie_event_notification(
    event_type: MealieEventType, shopping_list_id: str, use_internal_integration_id=False
) -> MealieEventNotification:
    return MealieEventNotification(
        event_id=random_string(),
        timestamp=datetime.utcnow(),
        version="nightly",
        title=random_string(),
        message=random_string(),
        event_type=event_type,
        integration_id=settings.mealie_integration_id if use_internal_integration_id else random_string(),
        document_data=json.dumps({"shoppingListId": shopping_list_id}),
    )


def build_todoist_webhook(event_type: TodoistEventType, todoist_user_id: str, project_id: str) -> TodoistWebhook:
    return TodoistWebhook(
        version=9, event_name=event_type, user_id=todoist_user_id, initiator={}, event_data={"project_id": project_id}
    )


def build_alexa_list_event(
    operation: Operation, object_type: ObjectType, list_id: str, list_item_ids: list[str] | None = None
) -> AlexaListEvent:
    if not list_item_ids:
        if object_type is object_type.list_item:
            raise Exception("list item ids must be provided when using the list item object type")
        else:
            list_item_ids = []

    return AlexaListEvent(
        request_id=random_string(),
        timestamp=datetime.utcnow(),
        operation=operation,
        object_type=object_type,
        list_id=list_id,
        list_item_ids=list_item_ids,
    )


def send_mealie_event_notification(notification: MealieEventNotification, user: User) -> None:
    api_client = _get_api_client()

    params = {
        "username": user.username,
        "security_hash": user.configuration.mealie.security_hash if user.configuration.mealie else "",
    }
    response = api_client.post(
        event_handlers.router.url_path_for("mealie_event_notification_handler"),
        params=params,
        json=jsonable_encoder(notification.dict()),
    )
    response.raise_for_status()


def get_todoist_security_headers(webhook: TodoistWebhook) -> dict[str, str]:
    body = json.dumps(jsonable_encoder(webhook.dict())).encode("utf-8")
    hmac_signature = hmac.new(
        key=secrets.todoist_client_secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    )

    security_hash = base64.b64encode(hmac_signature.digest()).decode()
    return {"X-Todoist-Hmac-SHA256": security_hash}


def send_todoist_webhook(webhook: TodoistWebhook) -> None:
    api_client = _get_api_client()
    response = api_client.post(
        event_handlers.router.url_path_for("todoist_event_notification_handler"),
        headers=get_todoist_security_headers(webhook),
        json=jsonable_encoder(webhook.dict()),
    )
    response.raise_for_status()


def send_alexa_list_event(list_event: AlexaListEvent, user: User) -> None:
    api_client = _get_api_client()
    response = api_client.post(
        event_handlers.router.url_path_for("alexa_event_notification_handler"),
        headers=get_auth_headers(user),
        json=jsonable_encoder(list_event.dict()),
    )
    response.raise_for_status()
