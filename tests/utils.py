import random
import string
from datetime import timedelta
from typing import Optional

from fastapi.testclient import TestClient

from AppLambda.src.app import services
from AppLambda.src.models.core import User, UserInDB
from AppLambda.src.routes import core


def random_string(length=10) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length)).strip()


def random_email(length=10) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length)) + "@example.com"


def random_password(length=20) -> str:
    return random_string(length)


def random_bool() -> bool:
    return bool(random.getrandbits(1))


def random_int(min=-4294967296, max=4294967296) -> int:
    return random.randint(min, max)


def random_url(https=True) -> str:
    """all random URLs are the same length, with or without https (24 characters)"""

    return f"{'https' if https else 'http'}//{random_string(5 if https else 6)}.example.com"


def get_auth_headers(user: User, expires: Optional[timedelta] = None) -> dict[str, str]:
    if not expires:
        expires = timedelta(hours=1)

    token = services.token.create_token(user.username, expires)
    return {"Authorization": f"Bearer {token.access_token}"}


def create_user_with_known_credentials(api_client: TestClient, register=True) -> tuple[UserInDB, str]:
    """
    Creates a user and optionally registers them

    Returns the user and their password
    """
    username = random_email()
    password = random_password()
    form_data = {"username": username, "password": password}
    response = api_client.post(core.router.url_path_for("register"), data=form_data)
    response.raise_for_status()

    new_user = services.user.get_user(username, active_only=False)
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

    new_user = services.user.get_user(username)
    assert new_user
    assert not new_user.disabled
    assert not new_user.is_rate_limit_exempt
    assert not new_user.use_developer_routes

    return new_user, password
