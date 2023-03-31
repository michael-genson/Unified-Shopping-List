import time
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from freezegun import freeze_time
from pytest import MonkeyPatch

from AppLambda.src import config
from AppLambda.src.app import services
from AppLambda.src.models.core import User
from AppLambda.src.routes import core
from tests.utils import create_user_with_known_credentials, random_email, random_string


def test_register_new_user(user: User):
    # this fixture already runs through all of the standard registration flow,
    # so we don't need to do anything other than use the fixture
    pass


def test_register_new_user_email_case_insensitive(api_client: TestClient):
    username = random_email().upper()
    form_data = {"username": username, "password": random_string(20)}
    response = api_client.post(core.router.url_path_for("register"), data=form_data)
    response.raise_for_status()

    user = services.user.get_user(username, active_only=False)
    assert user
    assert user.username == username.lower()


def test_register_invalid_password(api_client: TestClient):
    username = random_email()
    form_data = {"username": username, "password": random_string(1)}
    response = api_client.post(core.router.url_path_for("register"), data=form_data)
    response.raise_for_status()

    # since the password was too short, the user should not be created
    user = services.user.get_user(username, active_only=False)
    assert not user


def test_register_existing_user(api_client: TestClient, user: User):
    existing_user = services.user.get_user(user.username, active_only=False)
    assert existing_user

    form_data = {"username": existing_user.username, "password": random_string(20)}
    response = api_client.post(core.router.url_path_for("register"), data=form_data)
    response.raise_for_status()

    existing_user_refetch = services.user.get_user(user.username, active_only=False)
    assert existing_user_refetch
    assert existing_user_refetch.hashed_password == existing_user.hashed_password
    assert not existing_user_refetch.disabled
    assert existing_user_refetch.last_registration_token == existing_user.last_registration_token


def test_register_user_not_whitelisted(api_client: TestClient, monkeypatch: MonkeyPatch):
    with monkeypatch.context() as mp:
        mp.setattr(config, "USE_WHITELIST", True)
        username = random_email()
        form_data = {"username": username, "password": random_string(1)}
        response = api_client.post(core.router.url_path_for("register"), data=form_data)
        response.raise_for_status()

        # since the the user is not whitelisted, the user should not be created
        user = services.user.get_user(username, active_only=False)
        assert not user


def test_register_invalid_registration_token(api_client: TestClient):
    user, _ = create_user_with_known_credentials(api_client, register=False)
    assert user
    assert user.disabled

    response = api_client.get(
        core.router.url_path_for("complete_registration"),
        params={"registration_token": random_string()},
    )
    response.raise_for_status()
    user = services.user.get_user(user.username, active_only=False)
    assert user
    assert user.disabled

    response = api_client.get(core.router.url_path_for("complete_registration"))
    response.raise_for_status()
    user = services.user.get_user(user.username, active_only=False)
    assert user
    assert user.disabled


def test_register_old_token(api_client: TestClient):
    original_user, password = create_user_with_known_credentials(api_client, register=False)
    time.sleep(1)  # make sure registration token is replaced
    form_data = {"username": original_user.username, "password": password}
    response = api_client.post(core.router.url_path_for("register"), data=form_data)
    response.raise_for_status()

    refreshed_user = services.user.get_user(original_user.username, active_only=False)
    assert refreshed_user

    # try old token
    response = api_client.get(
        core.router.url_path_for("complete_registration"),
        params={"registration_token": original_user.last_registration_token},
    )
    response.raise_for_status()
    user = services.user.get_user(original_user.username, active_only=False)
    assert user
    assert user.disabled

    # try new token
    response = api_client.get(
        core.router.url_path_for("complete_registration"),
        params={"registration_token": refreshed_user.last_registration_token},
    )
    response.raise_for_status()

    user = services.user.get_user(refreshed_user.username)
    assert user
    assert not user.disabled


def test_register_expired_token(api_client: TestClient):
    user, _ = create_user_with_known_credentials(api_client, register=False)
    with freeze_time(datetime.now() + timedelta(days=999)):
        # try to use invalid token
        response = api_client.get(
            core.router.url_path_for("complete_registration"),
            params={"registration_token": user.last_registration_token},
        )
        response.raise_for_status()

        user = services.user.get_user(user.username, active_only=False)
        assert user
        assert user.disabled
