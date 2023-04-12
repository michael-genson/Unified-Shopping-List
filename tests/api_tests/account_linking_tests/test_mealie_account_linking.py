import random

from fastapi.testclient import TestClient

from AppLambda.src.models.account_linking import UserMealieConfiguration
from AppLambda.src.models.core import User
from AppLambda.src.models.mealie import AuthToken
from AppLambda.src.routes import account_linking
from AppLambda.src.services.auth_token import AuthTokenService
from AppLambda.src.services.user import UserService
from tests.fixtures.databases.mealie.router import MockDBKey, MockMealieServer
from tests.utils import get_auth_headers, random_string, random_url


def test_mealie_link_create(
    token_service: AuthTokenService,
    user_service: UserService,
    mealie_server: MockMealieServer,
    api_client: TestClient,
    user: User,
    mealie_api_tokens: list[AuthToken],
):
    notifier_data = mealie_server.get_all_records(MockDBKey.notifiers)
    existing_notifiers = len(notifier_data)

    api_token = random.choice(mealie_api_tokens)
    params = {"baseUrl": random_url(), "initialAuthToken": api_token.token}
    response = api_client.post(
        account_linking.api_router.url_path_for("link_mealie_account"),
        params=params,
        headers=get_auth_headers(token_service, user),
    )
    response.raise_for_status()
    new_config = UserMealieConfiguration.parse_obj(response.json())
    assert new_config.is_valid

    # confirm a new auth token was generated
    assert new_config.auth_token
    assert new_config.auth_token_id != api_token.id
    assert new_config.auth_token != api_token

    # confirm a new notifier was created
    notifier_data = mealie_server.get_all_records(MockDBKey.notifiers)
    assert len(notifier_data) == existing_notifiers + 1

    # confirm the user is updated
    updated_user = user_service.get_user(user.username)
    assert updated_user
    assert updated_user.is_linked_to_mealie
    assert updated_user.configuration.mealie == new_config


def test_mealie_link_create_with_invalid_token(
    token_service: AuthTokenService,
    user_service: UserService,
    mealie_server: MockMealieServer,
    api_client: TestClient,
    user: User,
):
    existing_notifier_data = mealie_server.get_all_records(MockDBKey.notifiers)

    params = {"baseUrl": random_url(), "initialAuthToken": random_string()}
    response = api_client.post(
        account_linking.api_router.url_path_for("link_mealie_account"),
        params=params,
        headers=get_auth_headers(token_service, user),
    )
    assert response.status_code == 400

    # confirm a new notifier was not created
    new_notifier_data = mealie_server.get_all_records(MockDBKey.notifiers)
    assert new_notifier_data == existing_notifier_data

    # confirm the user is not updated
    updated_user = user_service.get_user(user.username)
    assert updated_user
    assert not updated_user.is_linked_to_mealie
    assert not updated_user.configuration.mealie


def test_mealie_link_update(
    token_service: AuthTokenService, user_service: UserService, api_client: TestClient, user_linked: User
):
    existing_config = user_linked.configuration.mealie
    assert existing_config

    params = {
        "useFoods": not existing_config.use_foods,
        "overwriteOriginalItemNames": existing_config.overwrite_original_item_names,
        "confidenceThreshold": existing_config.confidence_threshold,
    }
    response = api_client.put(
        account_linking.api_router.url_path_for("update_mealie_account_link"),
        params=params,
        headers=get_auth_headers(token_service, user_linked),
    )
    response.raise_for_status()

    updated_user = user_service.get_user(user_linked.username)
    assert updated_user

    assert updated_user.is_linked_to_mealie
    updated_config = updated_user.configuration.mealie
    assert updated_config

    assert updated_config.use_foods is not None
    assert updated_config.use_foods is not bool(existing_config.use_foods)
    assert updated_config.overwrite_original_item_names == existing_config.overwrite_original_item_names
    assert updated_config.confidence_threshold == existing_config.confidence_threshold


def test_mealie_link_update_not_linked(
    token_service: AuthTokenService, user_service: UserService, api_client: TestClient, user: User
):
    response = api_client.put(
        account_linking.api_router.url_path_for("update_mealie_account_link"),
        headers=get_auth_headers(token_service, user),
    )
    assert response.status_code == 401

    updated_user = user_service.get_user(user.username)
    assert updated_user
    assert not updated_user.is_linked_to_mealie
    assert not updated_user.configuration.mealie


def test_mealie_link_delete(
    token_service: AuthTokenService,
    user_service: UserService,
    mealie_server: MockMealieServer,
    api_client: TestClient,
    user_linked: User,
):
    assert user_linked.is_linked_to_mealie

    notifier_data = mealie_server.get_all_records(MockDBKey.notifiers)
    existing_notifiers = len(notifier_data)
    assert existing_notifiers

    api_token_data = mealie_server.get_all_records(MockDBKey.user_api_tokens)
    existing_tokens = len(api_token_data)
    assert existing_tokens

    response = api_client.delete(
        account_linking.api_router.url_path_for("unlink_mealie_account"),
        headers=get_auth_headers(token_service, user_linked),
    )
    response.raise_for_status()

    # verify user is no longer linked to mealie
    updated_user = user_service.get_user(user_linked.username)
    assert updated_user
    assert not updated_user.is_linked_to_mealie
    assert not updated_user.configuration.mealie

    # verify the notifier and api token were deleted
    notifier_data = mealie_server.get_all_records(MockDBKey.notifiers)
    assert len(notifier_data) == existing_notifiers - 1

    api_token_data = mealie_server.get_all_records(MockDBKey.user_api_tokens)
    assert len(api_token_data) == existing_tokens - 1


def test_mealie_link_delete_not_linked(
    token_service: AuthTokenService,
    user_service: UserService,
    mealie_server: MockMealieServer,
    api_client: TestClient,
    user: User,
):
    notifier_data = mealie_server.get_all_records(MockDBKey.notifiers)
    existing_notifiers = len(notifier_data)

    api_token_data = mealie_server.get_all_records(MockDBKey.user_api_tokens)
    existing_tokens = len(api_token_data)

    # the response should come back okay, but not do anything
    response = api_client.delete(
        account_linking.api_router.url_path_for("unlink_mealie_account"), headers=get_auth_headers(token_service, user)
    )
    response.raise_for_status()

    # verify user still isn't linked
    updated_user = user_service.get_user(user.username)
    assert updated_user
    assert not updated_user.is_linked_to_mealie
    assert not updated_user.configuration.mealie

    # verify notifiers and api tokens are unchanged
    notifier_data = mealie_server.get_all_records(MockDBKey.notifiers)
    assert len(notifier_data) == existing_notifiers

    api_token_data = mealie_server.get_all_records(MockDBKey.user_api_tokens)
    assert len(api_token_data) == existing_tokens
