from unittest import mock

import pytest
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient
from requests import HTTPError

from AppLambda.src.app import settings
from AppLambda.src.models.alexa import ObjectType, Operation
from AppLambda.src.routes import event_handlers
from tests.fixtures.clients.fixture_sqsfifo_client import MockSQSFIFO
from tests.fixtures.fixture_users import MockLinkedUserAndData
from tests.utils.event_handlers import build_alexa_list_event
from tests.utils.info import fully_qualified_name
from tests.utils.users import get_auth_headers


def test_alexa_event_handler_send_to_queue(api_client: TestClient, user_data_with_items: MockLinkedUserAndData):
    assert user_data_with_items.alexa_list.items

    list_event = build_alexa_list_event(
        Operation.create,
        ObjectType.list_item,
        list_id=user_data_with_items.alexa_list.list_id,
        list_item_ids=[item.id for item in user_data_with_items.alexa_list.items],
    )
    with mock.patch(fully_qualified_name(MockSQSFIFO.send_message)) as mocked_sync_handler:
        response = api_client.post(
            event_handlers.router.url_path_for("alexa_event_notification_handler"),
            headers=get_auth_headers(user_data_with_items.user),
            json=jsonable_encoder(list_event.dict()),
        )
        response.raise_for_status()
        assert mocked_sync_handler.called


def test_alexa_event_handler_rate_limit(api_client: TestClient, user_data_with_items: MockLinkedUserAndData):
    assert user_data_with_items.alexa_list.items

    list_event = build_alexa_list_event(
        Operation.create,
        ObjectType.list_item,
        list_id=user_data_with_items.alexa_list.list_id,
        list_item_ids=[item.id for item in user_data_with_items.alexa_list.items],
    )

    with pytest.raises(HTTPError) as e_info:
        for _ in range(settings.rate_limit_minutely_sync + 1):
            response = api_client.post(
                event_handlers.router.url_path_for("alexa_event_notification_handler"),
                headers=get_auth_headers(user_data_with_items.user),
                json=jsonable_encoder(list_event.dict()),
            )
            response.raise_for_status()

    assert e_info.value.response.status_code == 429
