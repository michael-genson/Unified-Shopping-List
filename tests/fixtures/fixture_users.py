import random

from fastapi.testclient import TestClient
from pytest import fixture

from AppLambda.src.models.core import User
from AppLambda.src.models.mealie import AuthToken
from AppLambda.src.routes import account_linking
from AppLambda.src.services.auth_token import AuthTokenService
from AppLambda.src.services.user import UserService

from ..utils import create_user_with_known_credentials, get_auth_headers, random_url


@fixture()
def user(user_service: UserService, api_client: TestClient) -> User:
    user, _ = create_user_with_known_credentials(user_service, api_client)
    return user.cast(User)


@fixture()
def user_linked_mealie(
    token_service: AuthTokenService,
    user_service: UserService,
    api_client: TestClient,
    user: User,
    mealie_api_tokens: list[AuthToken],
) -> User:
    api_token = random.choice(mealie_api_tokens)
    params = {"baseUrl": random_url(), "initialAuthToken": api_token.token}
    response = api_client.post(
        account_linking.api_router.url_path_for("link_mealie_account"),
        params=params,
        headers=get_auth_headers(token_service, user),
    )
    response.raise_for_status()

    # disable config options
    response = api_client.put(
        account_linking.api_router.url_path_for("update_mealie_account_link"),
        params={"useFoods": False, "overwriteOriginalItemNames": False},
        headers=get_auth_headers(token_service, user),
    )
    response.raise_for_status()

    linked_user = user_service.get_user(user.username)
    assert linked_user
    return linked_user.cast(User)


@fixture()
def user_linked_mealie_use_foods(
    token_service: AuthTokenService,
    user_service: UserService,
    api_client: TestClient,
    user_linked_mealie: User,
) -> User:
    response = api_client.put(
        account_linking.api_router.url_path_for("update_mealie_account_link"),
        params={"useFoods": True, "overwriteOriginalItemNames": False},
        headers=get_auth_headers(token_service, user_linked_mealie),
    )
    response.raise_for_status()

    user = user_service.get_user(user_linked_mealie.username)
    assert user
    return user.cast(User)


@fixture()
def user_linked_mealie_overwrite_names(
    token_service: AuthTokenService,
    user_service: UserService,
    api_client: TestClient,
    user_linked_mealie_use_foods: User,
) -> User:
    response = api_client.put(
        account_linking.api_router.url_path_for("update_mealie_account_link"),
        params={"useFoods": True, "overwriteOriginalItemNames": True},
        headers=get_auth_headers(token_service, user_linked_mealie_use_foods),
    )
    response.raise_for_status()

    user = user_service.get_user(user_linked_mealie_use_foods.username)
    assert user
    return user.cast(User)
