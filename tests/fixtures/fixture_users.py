from datetime import timedelta

from fastapi.testclient import TestClient
from pytest import fixture

from AppLambda.src.app import services
from AppLambda.src.models.core import User
from AppLambda.src.routes import core

from ..utils import random_email, random_string


@fixture()
def user(api_client: TestClient) -> User:
    username = random_email()
    form_data = {"username": username, "password": random_string(20)}
    response = api_client.post(core.router.url_path_for("register"), data=form_data)
    response.raise_for_status()

    # get confirmation token from the backend and complete registration
    user = services.user.get_user(username, active_only=False)
    assert user
    assert user.disabled
    assert not user.is_rate_limit_exempt
    assert not user.use_developer_routes

    response = api_client.get(
        core.router.url_path_for("complete_registration"),
        params={"registration_token": user.last_registration_token},
    )
    response.raise_for_status()

    user = services.user.get_user(username)
    assert user
    assert not user.disabled
    assert not user.is_rate_limit_exempt
    assert not user.use_developer_routes

    return user.cast(User)


@fixture()
def user_token(user: User) -> str:
    token = services.token.create_token(user.username, timedelta(hours=1))
    return token.access_token
