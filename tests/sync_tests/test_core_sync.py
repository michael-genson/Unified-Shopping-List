import random
from unittest import mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from AppLambda.src.handlers.core import SQSSyncMessageHandler
from AppLambda.src.models.aws import SQSMessage
from AppLambda.src.models.core import User
from AppLambda.src.models.mealie import MealieEventType, MealieShoppingListOut, MealieSyncEvent
from AppLambda.src.routes import event_handlers
from tests.fixtures.fixture_users import MockLinkedUserAndData
from tests.utils.event_handlers import build_mealie_event_notification, send_mealie_event_notification
from tests.utils.generators import random_string
from tests.utils.info import fully_qualified_name


def test_bulk_sync_events_only_fire_once(api_client: TestClient, user_data_with_items: MockLinkedUserAndData):
    sync_event = MealieSyncEvent(
        username=user_data_with_items.user.username, shopping_list_id=user_data_with_items.mealie_list.id
    )
    messages = [
        SQSMessage(
            message_id=str(uuid4()),
            receipt_handle=random_string(),
            body=sync_event.json(),
            attributes={},
            message_attributes={},
        )
        for _ in range(10)
    ]

    with mock.patch(
        fully_qualified_name(SQSSyncMessageHandler.handle_message), return_value="Mealie"
    ) as mocked_message_handler:
        response = api_client.post(
            event_handlers.router.url_path_for("sqs_sync_event_handler"),
            json={"Records": [message.dict() for message in messages]},
        )
        response.raise_for_status()
        assert mocked_message_handler.call_count == 1


@pytest.mark.parametrize(
    "use_invalid_client_id, use_invalid_client_secret, expect_call",
    [
        (True, False, False),
        (False, True, False),
        (True, True, False),
        (False, False, True),
    ],
)
def test_invalid_client_keys(
    use_invalid_client_id: bool,
    use_invalid_client_secret: bool,
    expect_call: bool,
    api_client: TestClient,
    user_data: MockLinkedUserAndData,
):
    sync_event = MealieSyncEvent(username=user_data.user.username, shopping_list_id=user_data.mealie_list.id)
    if use_invalid_client_id:
        sync_event.client_id = random_string()
    if use_invalid_client_secret:
        sync_event.client_secret = random_string()

    message = SQSMessage(
        message_id=str(uuid4()),
        receipt_handle=random_string(),
        body=sync_event.json(),
        attributes={},
        message_attributes={},
    )

    with mock.patch(fully_qualified_name(SQSSyncMessageHandler.handle_message)) as mocked_message_handler:
        response = api_client.post(
            event_handlers.router.url_path_for("sqs_sync_event_handler"), json={"Records": [message.dict()]}
        )
        response.raise_for_status()
        if not expect_call:
            assert not mocked_message_handler.call_count
        else:
            assert mocked_message_handler.call_count == 1


def test_invalid_username(user_data: MockLinkedUserAndData):
    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, user_data.mealie_list.id)
    user_data.user.username = random_string()
    with mock.patch(fully_qualified_name(SQSSyncMessageHandler.handle_message)) as mocked_message_handler:
        send_mealie_event_notification(event, user_data.user)
        assert not mocked_message_handler.call_count


def test_user_not_linked_to_mealie(user: User, mealie_shopping_lists: list[MealieShoppingListOut]):
    shopping_list_id = random.choice(mealie_shopping_lists).id
    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, shopping_list_id)
    with mock.patch(fully_qualified_name(SQSSyncMessageHandler.handle_message)) as mocked_message_handler:
        send_mealie_event_notification(event, user)
        assert not mocked_message_handler.call_count
