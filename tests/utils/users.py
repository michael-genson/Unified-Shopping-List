from datetime import timedelta
from typing import Optional

from fastapi.testclient import TestClient

from AppLambda.src.models.core import User, UserInDB
from AppLambda.src.routes import core
from AppLambda.src.services.auth_token import AuthTokenService
from AppLambda.src.services.user import UserService

from .generators import random_email, random_password


def get_auth_headers(
    token_service: AuthTokenService, user: User, expires: Optional[timedelta] = None
) -> dict[str, str]:
    if not expires:
        expires = timedelta(hours=1)

    token = token_service.create_token(user.username, expires)
    return {"Authorization": f"Bearer {token.access_token}"}


def create_user_with_known_credentials(
    user_service: UserService, api_client: TestClient, register=True
) -> tuple[UserInDB, str]:
    """
    Creates a user and optionally registers them

    Returns the user and their password
    """
    username = random_email()
    password = random_password()
    form_data = {"username": username, "password": password}
    response = api_client.post(core.router.url_path_for("register"), data=form_data)
    response.raise_for_status()

    new_user = user_service.get_user(username, active_only=False)
    assert new_user
    assert new_user.disabled
    assert not new_user.is_rate_limit_exempt
    assert not new_user.use_developer_routes

    if not register:
        return new_user, password

    # get confirmation token from the backend and complete registration
    response = api_client.get(
        core.router.url_path_for("complete_registration"),
        params={"registration_token": new_user.last_registration_token},
    )
    response.raise_for_status()

    new_user = user_service.get_user(username)
    assert new_user
    assert not new_user.disabled
    assert not new_user.is_rate_limit_exempt
    assert not new_user.use_developer_routes

    return new_user, password
