from unittest import mock

import pytest
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient
from requests import HTTPError

from AppLambda.src import config
from AppLambda.src.models.mealie import MealieEventType
from AppLambda.src.routes import event_handlers
from tests.fixtures.clients.fixture_sqsfifo_client import MockSQSFIFO
from tests.fixtures.fixture_users import MockLinkedUserAndData
from tests.utils.event_handlers import build_mealie_event_notification
from tests.utils.generators import random_string
from tests.utils.info import fully_qualified_name
from tests.utils.users import create_user_with_known_credentials


@pytest.mark.parametrize(
    (
        "use_valid_type, use_random_integration_id, use_non_null_shopping_list_id,"
        "use_valid_username, use_linked_user, use_valid_security_hash, should_send_message"
    ),
    [
        (False, True, True, True, True, True, False),
        (True, False, True, True, True, True, False),
        (True, True, False, True, True, True, False),
        (True, True, True, False, True, True, False),
        (True, True, True, True, False, True, False),
        (True, True, True, True, True, False, False),
        (True, True, True, True, True, True, True),
    ],
)
def test_mealie_event_handler_send_to_queue(
    use_valid_type: bool,
    use_random_integration_id: bool,
    use_non_null_shopping_list_id: bool,
    use_valid_username: bool,
    use_linked_user: bool,
    use_valid_security_hash: bool,
    should_send_message: bool,
    api_client: TestClient,
    user_data_with_items: MockLinkedUserAndData,
):
    linked_user = user_data_with_items.user
    assert linked_user.is_linked_to_mealie
    assert linked_user.configuration.mealie

    if not use_valid_type:
        event_type = MealieEventType.invalid
    else:
        event_type = MealieEventType.shopping_list_updated

    if not use_non_null_shopping_list_id:
        shopping_list_id = ""
    else:
        shopping_list_id = user_data_with_items.mealie_list.id

    if not use_valid_username:
        username = random_string()
    elif not use_linked_user:
        _user, _ = create_user_with_known_credentials(api_client)
        username = _user.username
    else:
        username = linked_user.username

    if not use_valid_security_hash:
        security_hash = random_string()
    else:
        security_hash = linked_user.configuration.mealie.security_hash

    event = build_mealie_event_notification(
        event_type, shopping_list_id, use_internal_integration_id=not use_random_integration_id
    )

    with mock.patch(fully_qualified_name(MockSQSFIFO.send_message)) as mocked_sync_handler:
        params = {"username": username, "security_hash": security_hash}
        response = api_client.post(
            event_handlers.router.url_path_for("mealie_event_notification_handler"),
            params=params,
            json=jsonable_encoder(event.dict()),
        )
        response.raise_for_status()
        assert mocked_sync_handler.called is should_send_message


def test_mealie_event_handler_rate_limit(api_client: TestClient, user_data_with_items: MockLinkedUserAndData):
    user = user_data_with_items.user
    assert user.configuration.mealie
    assert not user.is_rate_limit_exempt
    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, user_data_with_items.mealie_list.id)

    with pytest.raises(HTTPError) as e_info:
        for _ in range(config.RATE_LIMIT_MINUTELY_SYNC + 1):
            event.event_id = random_string()

            params = {"username": user.username, "security_hash": user.configuration.mealie.security_hash}
            response = api_client.post(
                event_handlers.router.url_path_for("mealie_event_notification_handler"),
                params=params,
                json=jsonable_encoder(event.dict()),
            )
            response.raise_for_status()

    assert e_info.value.response.status_code == 429
