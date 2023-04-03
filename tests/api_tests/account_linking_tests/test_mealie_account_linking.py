import random

from fastapi.testclient import TestClient

from AppLambda.src.app import services
from AppLambda.src.models.account_linking import UserMealieConfiguration
from AppLambda.src.models.core import User
from AppLambda.src.models.mealie import AuthToken
from AppLambda.src.routes import account_linking
from tests.fixtures.clients.mealie.router import MockDBKey, MockMealieServer
from tests.utils import get_auth_headers, random_string, random_url


def test_link_to_mealie(
    mealie_server: MockMealieServer, api_client: TestClient, user: User, mealie_api_tokens: list[AuthToken]
):
    notifier_data = mealie_server.get_all_records(MockDBKey.notifiers)
    existing_notifiers = len(notifier_data)

    api_token = random.choice(mealie_api_tokens)
    params = {"baseUrl": random_url(), "initialAuthToken": api_token.token}
    response = api_client.post(
        account_linking.api_router.url_path_for("link_mealie_account"), params=params, headers=get_auth_headers(user)
    )
    response.raise_for_status()
    new_config = UserMealieConfiguration.parse_obj(response.json())

    # confirm a new auth token was generated
    assert new_config.auth_token
    assert new_config.auth_token_id != api_token.id
    assert new_config.auth_token != api_token

    # confirm a new notifier was created
    notifier_data = mealie_server.get_all_records(MockDBKey.notifiers)
    assert len(notifier_data) == existing_notifiers + 1

    # confirm the user is updated
    updated_user = services.user.get_user(user.username)
    assert updated_user
    assert updated_user.is_linked_to_mealie
    assert updated_user.configuration.mealie == new_config


def test_mealie_link_with_invalid_token(mealie_server: MockMealieServer, api_client: TestClient, user: User):
    existing_notifier_data = mealie_server.get_all_records(MockDBKey.notifiers)

    params = {"baseUrl": random_url(), "initialAuthToken": random_string()}
    response = api_client.post(
        account_linking.api_router.url_path_for("link_mealie_account"), params=params, headers=get_auth_headers(user)
    )
    assert response.status_code == 400

    # confirm a new notifier was not created
    new_notifier_data = mealie_server.get_all_records(MockDBKey.notifiers)
    assert new_notifier_data == existing_notifier_data

    # confirm the user is not updated
    updated_user = services.user.get_user(user.username)
    assert updated_user
    assert not updated_user.is_linked_to_mealie
    assert not updated_user.configuration.mealie
