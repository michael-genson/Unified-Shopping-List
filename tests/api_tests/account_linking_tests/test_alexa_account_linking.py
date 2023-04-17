import base64
import hashlib
import hmac
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from AppLambda.src import config
from AppLambda.src.app_secrets import APP_CLIENT_ID, APP_CLIENT_SECRET  # TODO: remove secrets dependency
from AppLambda.src.models.account_linking import UserAlexaConfiguration
from AppLambda.src.models.core import Token, User
from AppLambda.src.routes import account_linking, alexa
from AppLambda.src.services.auth_token import AuthTokenService
from AppLambda.src.services.user import UserService
from tests.utils.generators import random_string, random_url
from tests.utils.users import get_auth_headers


def test_alexa_link_create(user_service: UserService, api_client: TestClient, user_linked_mealie: User):
    alexa_user_id = random_string()
    params = {"userId": alexa_user_id}
    response = api_client.post(
        account_linking.api_router.url_path_for("link_alexa_account"),
        params=params,
        headers=get_auth_headers(user_linked_mealie),
    )
    response.raise_for_status()
    new_config = UserAlexaConfiguration.parse_obj(response.json())
    assert new_config.is_valid

    # confirm the user is updated
    updated_user = user_service.get_user(user_linked_mealie.username)
    assert updated_user
    assert updated_user.is_linked_to_alexa
    assert updated_user.configuration.alexa == new_config
    assert updated_user.alexa_user_id == alexa_user_id


def test_alexa_link_delete(user_service: UserService, api_client: TestClient, user_linked: User):
    assert user_linked.is_linked_to_alexa
    response = api_client.delete(
        account_linking.api_router.url_path_for("unlink_alexa_account"),
        headers=get_auth_headers(user_linked),
    )
    response.raise_for_status()

    # verify user is no longer linked to alexa
    updated_user = user_service.get_user(user_linked.username)
    assert updated_user
    assert not updated_user.is_linked_to_alexa
    assert not updated_user.configuration.alexa

    # verify user is still linked to mealie
    assert updated_user.is_linked_to_mealie
    assert updated_user.configuration.mealie


def test_alexa_auth_handshake_authorize(
    token_service: AuthTokenService, api_client: TestClient, user_linked_mealie: User
):
    redirect_uri = random_url()
    state = random_string()

    new_token = token_service.create_token(user_linked_mealie.username)
    cookies = {"access_token": new_token.access_token}
    params = {
        "client_id": APP_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": random_string(),
        "scope": random_string(),
        "state": state,
    }
    response = api_client.get(
        alexa.auth_router.url_path_for("authorize_alexa_app"), cookies=cookies, params=params, allow_redirects=True
    )
    response.raise_for_status()

    response_url = response.history[-1].url  # since we are redirected, we need to check the previous response
    assert redirect_uri in response_url
    redirect_params = parse_qs(urlparse(response_url).query)

    assert "state" in redirect_params
    assert len(redirect_params["state"]) == 1
    assert redirect_params["state"][0] == state

    assert "code" in redirect_params
    assert len(redirect_params["code"]) == 1
    redirect_code = redirect_params["code"][0]
    assert token_service.get_username_from_token(redirect_code) == user_linked_mealie.username


def test_alexa_auth_handshake_authorize_invalid_client_id(
    token_service: AuthTokenService, api_client: TestClient, user_linked_mealie: User
):
    new_token = token_service.create_token(user_linked_mealie.username)
    cookies = {"access_token": new_token.access_token}
    params = {
        "client_id": random_string(),
        "redirect_uri": random_url(),
        "response_type": random_string(),
        "scope": random_string(),
        "state": random_string(),
    }
    response = api_client.get(
        alexa.auth_router.url_path_for("authorize_alexa_app"), cookies=cookies, params=params, allow_redirects=True
    )
    assert response.status_code == 400


def test_alexa_auth_handshake_get_token(
    token_service: AuthTokenService, api_client: TestClient, user_linked_mealie: User
):
    new_token = token_service.create_token(user_linked_mealie.username)
    data = {
        "grant_type": random_string(),
        "code": new_token.access_token,
        "client_id": APP_CLIENT_ID,
        "redirect_uri": random_url(),
    }
    response = api_client.post(alexa.auth_router.url_path_for("get_access_token"), data=data)
    response.raise_for_status()

    response_token = Token.parse_obj(response.json())
    assert token_service.get_username_from_token(response_token.access_token) == user_linked_mealie.username


def test_alexa_auth_handshake_get_token_invalid_client_id(
    token_service: AuthTokenService, api_client: TestClient, user_linked_mealie: User
):
    new_token = token_service.create_token(user_linked_mealie.username)
    data = {
        "grant_type": random_string(),
        "code": new_token.access_token,
        "client_id": random_string(),
        "redirect_uri": random_url(),
    }
    response = api_client.post(alexa.auth_router.url_path_for("get_access_token"), data=data)
    assert response.status_code == 400


def test_alexa_auth_handshake_unlink_user(user_service: UserService, api_client: TestClient, user_linked: User):
    assert user_linked.is_linked_to_alexa
    hmac_signature = hmac.new(
        key=APP_CLIENT_SECRET.encode("utf-8"),
        msg=APP_CLIENT_ID.encode("utf-8"),
        digestmod=hashlib.sha256,
    )

    security_hash = base64.b64encode(hmac_signature.digest()).decode()
    headers = {config.ALEXA_SECRET_HEADER_KEY: security_hash}
    url = alexa.auth_router.url_path_for("unlink_user_from_alexa_app") + f"?userId={user_linked.alexa_user_id}"
    response = api_client.delete(url, headers=headers)
    response.raise_for_status()

    user = user_service.get_user(user_linked.username)
    assert user
    assert not user.is_linked_to_alexa


def test_alexa_auth_handshake_unlink_user_invalid_security_hash(
    user_service: UserService, api_client: TestClient, user_linked: User
):
    assert user_linked.is_linked_to_alexa
    url = alexa.auth_router.url_path_for("unlink_user_from_alexa_app") + f"?userId={user_linked.alexa_user_id}"

    response = api_client.delete(url)
    assert response.status_code == 400
    user = user_service.get_user(user_linked.username)
    assert user
    assert user.is_linked_to_alexa

    headers = {config.ALEXA_SECRET_HEADER_KEY: random_string()}
    response = api_client.delete(url, headers=headers)
    assert response.status_code == 400
    user = user_service.get_user(user_linked.username)
    assert user
    assert user.is_linked_to_alexa
