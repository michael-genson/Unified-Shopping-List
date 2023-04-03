import random

from fastapi.testclient import TestClient
from pytest import fixture

from AppLambda.src.app import services
from AppLambda.src.models.core import User
from AppLambda.src.models.mealie import AuthToken
from AppLambda.src.routes import account_linking

from ..utils import create_user_with_known_credentials, get_auth_headers, random_url


@fixture()
def user(api_client: TestClient) -> User:
    user, _ = create_user_with_known_credentials(api_client)
    return user.cast(User)


@fixture()
def user_linked_mealie(api_client: TestClient, user: User, mealie_api_tokens: list[AuthToken]) -> User:
    api_token = random.choice(mealie_api_tokens)
    params = {"baseUrl": random_url(), "initialAuthToken": api_token.token}
    response = api_client.post(
        account_linking.api_router.url_path_for("link_mealie_account"), params=params, headers=get_auth_headers(user)
    )
    response.raise_for_status()

    linked_user = services.user.get_user(user.username)
    assert linked_user
    return linked_user.cast(User)
