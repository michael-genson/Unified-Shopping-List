import random

from fastapi.testclient import TestClient
from pytest import fixture

from AppLambda.src.models.core import User
from AppLambda.src.models.mealie import AuthToken
from AppLambda.src.routes import account_linking
from AppLambda.src.services.user import UserService

from ..utils.generators import random_string, random_url
from ..utils.users import create_user_with_known_credentials, get_auth_headers


@fixture()
def user(api_client: TestClient) -> User:
    user, _ = create_user_with_known_credentials(api_client)
    return user.cast(User)


@fixture()
def user_linked_mealie(
    user_service: UserService, api_client: TestClient, user: User, mealie_api_tokens: list[AuthToken]
) -> User:
    """User that is only linked to Mealie"""

    api_token = random.choice(mealie_api_tokens)
    params = {"baseUrl": random_url(), "initialAuthToken": api_token.token}
    response = api_client.post(
        account_linking.api_router.url_path_for("link_mealie_account"),
        params=params,
        headers=get_auth_headers(user),
    )
    response.raise_for_status()

    linked_user = user_service.get_user(user.username)
    assert linked_user
    return linked_user.cast(User)


@fixture()
def user_linked(user_service: UserService, api_client: TestClient, user_linked_mealie: User) -> User:
    """User that is linked to all services"""

    # link user to Alexa
    params = {"userId": random_string()}
    response = api_client.post(
        account_linking.api_router.url_path_for("link_alexa_account"),
        params=params,
        headers=get_auth_headers(user_linked_mealie),
    )
    response.raise_for_status()

    # link user to Todoist
    params = {"accessToken": random_string()}
    response = api_client.post(
        account_linking.api_router.url_path_for("link_todoist_account"),
        params=params,
        headers=get_auth_headers(user_linked_mealie),
    )
    response.raise_for_status()

    linked_user = user_service.get_user(user_linked_mealie.username)
    assert linked_user
    return linked_user.cast(User)
