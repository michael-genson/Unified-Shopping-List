from datetime import datetime, timedelta

from freezegun import freeze_time
from jose import jwt

from AppLambda.src.app import secrets
from AppLambda.src.services.auth_token import AuthTokenService
from tests.utils.generators import random_string


def test_auth_token_service_create_token(token_service: AuthTokenService):
    username = random_string()
    token = token_service.create_token(username)
    assert token.token_type == "Bearer"

    decoded_token = jwt.decode(token.access_token, secrets.db_secret_key, secrets.db_algorithm)
    assert decoded_token.get("sub") == username


def test_auth_token_service_get_username_from_token(token_service: AuthTokenService):
    username = random_string()
    token = token_service.create_token(username)
    assert token_service.get_username_from_token(token.access_token) == username


def test_auth_token_service_refresh_token(token_service: AuthTokenService):
    username = random_string()
    token = token_service.create_token(username)

    decoded_token = jwt.decode(token.access_token, secrets.db_secret_key, secrets.db_algorithm)
    initial_expiration: datetime | None = decoded_token.get("exp")
    assert initial_expiration

    with freeze_time(datetime.now() + timedelta(seconds=10)):
        new_token = token_service.refresh_token(token.access_token)
        decoded_token = jwt.decode(new_token.access_token, secrets.db_secret_key, secrets.db_algorithm)
        new_expiration: datetime | None = decoded_token.get("exp")
        assert new_expiration
        assert new_expiration > initial_expiration
