from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from AppLambda.src import config
from AppLambda.src.app import services
from AppLambda.src.models.core import Token, User
from AppLambda.src.routes import auth, core
from tests.utils import create_user_with_known_credentials, get_auth_headers, random_email, random_string


def test_get_logged_in_user(api_client: TestClient, user: User):
    response = api_client.get(auth.router.url_path_for("get_logged_in_user"), headers=get_auth_headers(user))
    response.raise_for_status()

    current_user = User.parse_obj(response.json())
    assert current_user.username == user.username


def test_log_in(api_client: TestClient):
    user, password = create_user_with_known_credentials(api_client)
    form_data = {"username": user.username, "password": password}

    # log in using email and password
    response = api_client.post(core.router.url_path_for("log_in"), data=form_data)
    response.raise_for_status()
    assert (access_token := response.cookies.get("access_token"))

    # check that the access token works
    headers = {"Authorization": f"Bearer {access_token}"}
    response = api_client.get(auth.router.url_path_for("get_logged_in_user"), headers=headers)
    response.raise_for_status()

    current_user = User.parse_obj(response.json())
    assert current_user.username == user.username

    # get access token using email and password
    response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
    response.raise_for_status()

    token = Token.parse_obj(response.json())
    headers = {"Authorization": f"Bearer {token.access_token}"}

    # check that the access token works
    response = api_client.get(auth.router.url_path_for("get_logged_in_user"), headers=headers)
    response.raise_for_status()

    current_user = User.parse_obj(response.json())
    assert current_user.username == user.username


def test_login_user_invalid_username(api_client: TestClient):
    form_data = {"username": random_email(), "password": random_string(20)}

    # try to log in
    response = api_client.post(core.router.url_path_for("log_in"), data=form_data)
    response.raise_for_status()
    assert not response.cookies.get("access_token")

    # try to get access token
    response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
    assert response.status_code == 401


def test_login_wrong_password(api_client: TestClient, user: User):
    form_data = {"username": user.username, "password": random_string(20)}

    # try to log in
    response = api_client.post(core.router.url_path_for("log_in"), data=form_data)
    response.raise_for_status()
    assert not response.cookies.get("access_token")

    # try to get access token
    response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
    assert response.status_code == 401


def test_login_not_registered(api_client: TestClient):
    user, password = create_user_with_known_credentials(api_client, register=False)
    form_data = {"username": user.username, "password": password}

    # try to log in before finishing registration
    response = api_client.post(core.router.url_path_for("log_in"), data=form_data)
    response.raise_for_status()
    assert not response.cookies.get("access_token")

    # try to get access token before finishing registration
    response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
    assert response.status_code == 401


def test_login_disabled(api_client: TestClient):
    user, password = create_user_with_known_credentials(api_client)
    form_data = {"username": user.username, "password": password}

    # disable user
    user.disabled = True
    services.user.update_user(user)

    # try to log in
    response = api_client.post(core.router.url_path_for("log_in"), data=form_data)
    response.raise_for_status()
    assert not response.cookies.get("access_token")

    # try to get access token
    response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
    assert response.status_code == 401


def test_login_not_whitelisted(api_client: TestClient, monkeypatch: MonkeyPatch):
    user, password = create_user_with_known_credentials(api_client)
    form_data = {"username": user.username, "password": password}

    # log in normally
    response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
    response.raise_for_status()
    Token.parse_obj(response.json())

    # enable whitelist and try to login
    with monkeypatch.context() as mp:
        mp.setattr(config, "USE_WHITELIST", True)
        response = api_client.post(core.router.url_path_for("log_in"), data=form_data)
        response.raise_for_status()
        assert not response.cookies.get("access_token")

        # try to get access token
        response = api_client.post(auth.router.url_path_for("log_in_for_access_token"), data=form_data)
        assert response.status_code == 401
        assert not response.cookies.get("access_token")
