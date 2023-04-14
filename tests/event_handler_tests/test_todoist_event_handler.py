from unittest import mock

import pytest
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient
from requests import HTTPError

from AppLambda.src import config
from AppLambda.src.models.todoist import TodoistEventType
from AppLambda.src.routes import event_handlers
from tests.fixtures.clients.fixture_sqsfifo_client import MockSQSFIFO
from tests.fixtures.fixture_users import MockLinkedUserAndData
from tests.utils.event_handlers import build_todoist_webhook, get_todoist_security_headers
from tests.utils.generators import random_string
from tests.utils.info import fully_qualified_name


@pytest.mark.parametrize(
    "use_valid_type, use_non_null_project_id, use_valid_security_header, should_send_message",
    [
        (False, True, True, False),
        (True, False, True, False),
        (True, True, False, False),
        (True, True, True, True),
    ],
)
def test_todoist_event_handler_send_to_queue(
    use_valid_type: bool,
    use_non_null_project_id: bool,
    use_valid_security_header: bool,
    should_send_message: bool,
    api_client: TestClient,
    user_data_with_items: MockLinkedUserAndData,
):
    linked_user = user_data_with_items.user
    assert linked_user.is_linked_to_mealie
    assert linked_user.is_linked_to_todoist
    assert linked_user.todoist_user_id

    if not use_valid_type:
        event_type = TodoistEventType.invalid
    else:
        event_type = TodoistEventType.item_added

    if not use_non_null_project_id:
        project_id = ""
    else:
        project_id = user_data_with_items.todoist_data.project.id

    webhook = build_todoist_webhook(event_type, linked_user.todoist_user_id, project_id)
    if not use_valid_security_header:
        headers = {"X-Todoist-Hmac-SHA256": random_string()}
    else:
        headers = get_todoist_security_headers(webhook)

    with mock.patch(fully_qualified_name(MockSQSFIFO.send_message)) as mocked_sync_handler:
        response = api_client.post(
            event_handlers.router.url_path_for("todoist_event_notification_handler"),
            headers=headers,
            json=jsonable_encoder(webhook.dict()),
        )
        response.raise_for_status()
        assert mocked_sync_handler.called is should_send_message


def test_todoist_event_handler_rate_limit(api_client: TestClient, user_data_with_items: MockLinkedUserAndData):
    linked_user = user_data_with_items.user
    assert linked_user.is_linked_to_mealie
    assert linked_user.is_linked_to_todoist
    assert linked_user.todoist_user_id
    webhook = build_todoist_webhook(
        TodoistEventType.item_added, linked_user.todoist_user_id, user_data_with_items.todoist_data.project.id
    )

    with pytest.raises(HTTPError) as e_info:
        for _ in range(config.RATE_LIMIT_MINUTELY_SYNC + 1):
            response = api_client.post(
                event_handlers.router.url_path_for("todoist_event_notification_handler"),
                headers=get_todoist_security_headers(webhook),
                json=jsonable_encoder(webhook.dict()),
            )
            response.raise_for_status()

    assert e_info.value.response.status_code == 429
