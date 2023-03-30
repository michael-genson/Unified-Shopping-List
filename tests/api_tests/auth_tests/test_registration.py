from fastapi.testclient import TestClient

from AppLambda.src import config
from AppLambda.src.app import services
from AppLambda.src.models.core import User
from AppLambda.src.routes import core
from tests.utils import random_email, random_string


def test_new_user(user: User):
    # this fixture already runs through all of the standard registration flow,
    # so we don't need to do anything other than use the fixture
    pass


def test_new_user_email_case_insensitive(api_client: TestClient):
    username = random_email().upper()
    form_data = {"username": username, "password": random_string(20)}
    response = api_client.post(core.router.url_path_for("register"), data=form_data)
    response.raise_for_status()

    user = services.user.get_user(username, active_only=False)
    assert user
    assert user.username == username.lower()


def test_invalid_password(api_client: TestClient):
    username = random_email()
    form_data = {"username": username, "password": random_string(1)}
    response = api_client.post(core.router.url_path_for("register"), data=form_data)
    response.raise_for_status()

    # since the password was too short, the user should not be created
    user = services.user.get_user(username, active_only=False)
    assert not user


def test_existing_user(api_client: TestClient, user: User):
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


def test_user_not_whitelisted(api_client: TestClient):
    config.USE_WHITELIST = True

    username = random_email()
    form_data = {"username": username, "password": random_string(1)}
    response = api_client.post(core.router.url_path_for("register"), data=form_data)
    response.raise_for_status()

    # since the the user is not whitelisted, the user should not be created
    user = services.user.get_user(username, active_only=False)
    assert not user


def test_invalid_registration_token(api_client: TestClient):
    username = random_email()
    form_data = {"username": username, "password": random_string(20)}
    response = api_client.post(core.router.url_path_for("register"), data=form_data)
    response.raise_for_status()

    user = services.user.get_user(username, active_only=False)
    assert user
    assert user.disabled

    response = api_client.get(
        core.router.url_path_for("complete_registration"),
        params={"registration_token": random_string()},
    )
    response.raise_for_status()
    user = services.user.get_user(username, active_only=False)
    assert user
    assert user.disabled

    response = api_client.get(core.router.url_path_for("complete_registration"))
    response.raise_for_status()
    user = services.user.get_user(username, active_only=False)
    assert user
    assert user.disabled
