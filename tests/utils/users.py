from datetime import timedelta
from typing import Any, Optional

from fastapi.testclient import TestClient

from AppLambda.src.app import app
from AppLambda.src.models.account_linking import UserMealieConfigurationUpdate, UserTodoistConfigurationUpdate
from AppLambda.src.models.core import User, UserInDB
from AppLambda.src.routes import account_linking, core
from AppLambda.src.services.auth_token import AuthTokenService
from AppLambda.src.services.user import UserService

from .generators import random_email, random_password


def get_auth_headers(user: User, expires: Optional[timedelta] = None) -> dict[str, str]:
    token_service = AuthTokenService()
    if not expires:
        expires = timedelta(hours=1)

    token = token_service.create_token(user.username, expires)
    return {"Authorization": f"Bearer {token.access_token}"}


def create_user_with_known_credentials(api_client: TestClient, register=True) -> tuple[UserInDB, str]:
    """
    Creates a user and optionally registers them

    Returns the user and their password
    """
    token_service = AuthTokenService()
    user_service = UserService(token_service)

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


def _update_account_link(user: User, route: str, params: dict[str, Any]) -> User:
    token_service = AuthTokenService()
    user_service = UserService(token_service)
    api_client = TestClient(app)

    response = api_client.put(
        account_linking.api_router.url_path_for(route), params=params, headers=get_auth_headers(user)
    )
    response.raise_for_status()

    updated_user = user_service.get_user(user.username)
    assert updated_user
    return updated_user.cast(User)


def update_mealie_config(user: User, config: UserMealieConfigurationUpdate) -> User:
    return _update_account_link(user, "update_mealie_account_link", config.dict(by_alias=True))


def update_todoist_config(user: User, config: UserTodoistConfigurationUpdate) -> User:
    return _update_account_link(user, "update_todoist_account_link", config.dict(by_alias=True))
