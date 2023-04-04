import time
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from freezegun import freeze_time

from AppLambda.src.routes import auth, core
from AppLambda.src.services.user import UserService
from tests.utils import create_user_with_known_credentials, random_email, random_password, random_string


def get_password_reset_token(user_service: UserService, api_client: TestClient, username: str) -> str:
    response = api_client.post(core.router.url_path_for("initiate_password_reset_email"), data={"username": username})
    response.raise_for_status()

    user = user_service.get_user(username, active_only=False)
    assert user
    assert user.last_password_reset_token
    return user.last_password_reset_token


def test_reset_password(user_service: UserService, api_client: TestClient):
    existing_user, old_password = create_user_with_known_credentials(user_service, api_client)
    reset_token = get_password_reset_token(user_service, api_client, existing_user.username)

    new_password = random_password()
    response = api_client.post(
        core.router.url_path_for("reset_password"), params={"reset_token": reset_token}, data={"password": new_password}
    )
    response.raise_for_status()

    # log in with new password
    form_data = {"username": existing_user.username, "password": new_password}
    response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
    response.raise_for_status()

    # try to log in with old password
    form_data = {"username": existing_user.username, "password": old_password}
    response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
    assert response.status_code == 401


def test_reset_password_invalid_username(api_client: TestClient):
    response = api_client.post(
        core.router.url_path_for("initiate_password_reset_email"), data={"username": random_email()}
    )

    # even though this username is random, we should still respond okay
    response.raise_for_status()


def test_reset_password_invalid_token(user_service: UserService, api_client: TestClient):
    existing_user, old_password = create_user_with_known_credentials(user_service, api_client)
    get_password_reset_token(user_service, api_client, existing_user.username)

    # try invalid token
    new_password = random_password()
    response = api_client.post(
        core.router.url_path_for("reset_password"),
        params={"reset_token": random_string()},
        data={"password": new_password},
    )
    response.raise_for_status()

    # try no token
    response = api_client.post(
        core.router.url_path_for("reset_password"),
        data={"password": new_password},
    )
    response.raise_for_status()

    # try to log in with new password
    form_data = {"username": existing_user.username, "password": new_password}
    response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
    assert response.status_code == 401

    # log in with old password
    form_data = {"username": existing_user.username, "password": old_password}
    response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
    response.raise_for_status()


def test_reset_password_invalid_new_password(user_service: UserService, api_client: TestClient):
    existing_user, old_password = create_user_with_known_credentials(user_service, api_client)
    reset_token = get_password_reset_token(user_service, api_client, existing_user.username)

    # try invalid password
    new_password = random_string(1)
    response = api_client.post(
        core.router.url_path_for("reset_password"),
        params={"reset_token": reset_token},
        data={"password": new_password},
    )
    response.raise_for_status()

    # try to log in with new password
    form_data = {"username": existing_user.username, "password": new_password}
    response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
    assert response.status_code == 401

    # log in with old password
    form_data = {"username": existing_user.username, "password": old_password}
    response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
    response.raise_for_status()


def test_reset_password_old_token(user_service: UserService, api_client: TestClient):
    existing_user, old_password = create_user_with_known_credentials(user_service, api_client)
    invalid_reset_token = get_password_reset_token(user_service, api_client, existing_user.username)
    time.sleep(1)  # make sure valid_reset_token replaces invalid_reset_token
    valid_reset_token = get_password_reset_token(user_service, api_client, existing_user.username)

    # try to use invalid token
    new_password = random_password()
    response = api_client.post(
        core.router.url_path_for("reset_password"),
        params={"reset_token": invalid_reset_token},
        data={"password": new_password},
    )
    response.raise_for_status()

    # try to log in with new password
    form_data = {"username": existing_user.username, "password": new_password}
    response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
    assert response.status_code == 401

    # log in with old password
    form_data = {"username": existing_user.username, "password": old_password}
    response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
    response.raise_for_status()

    # use valid token
    new_password = random_password()
    response = api_client.post(
        core.router.url_path_for("reset_password"),
        params={"reset_token": valid_reset_token},
        data={"password": new_password},
    )
    response.raise_for_status()

    # log in with new password
    form_data = {"username": existing_user.username, "password": new_password}
    response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
    response.raise_for_status()

    # try to log in with old password
    form_data = {"username": existing_user.username, "password": old_password}
    response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
    assert response.status_code == 401


def test_reset_password_expired_token(user_service: UserService, api_client: TestClient):
    existing_user, old_password = create_user_with_known_credentials(user_service, api_client)
    expired_reset_token = get_password_reset_token(user_service, api_client, existing_user.username)

    with freeze_time(datetime.now() + timedelta(days=999)):
        # try to use invalid token
        new_password = random_password()
        response = api_client.post(
            core.router.url_path_for("reset_password"),
            params={"reset_token": expired_reset_token},
            data={"password": new_password},
        )
        response.raise_for_status()

        # try to log in with new password
        form_data = {"username": existing_user.username, "password": new_password}
        response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
        assert response.status_code == 401

        # log in with old password
        form_data = {"username": existing_user.username, "password": old_password}
        response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
        response.raise_for_status()
