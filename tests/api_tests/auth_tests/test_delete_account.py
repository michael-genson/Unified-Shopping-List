from fastapi.testclient import TestClient

from AppLambda.src.models.core import User
from AppLambda.src.routes import core
from AppLambda.src.services.auth_token import AuthTokenService
from AppLambda.src.services.user import UserService
from tests.utils import get_auth_headers


def test_delete_user(token_service: AuthTokenService, user_service: UserService, api_client: TestClient, user: User):
    response = api_client.post(core.router.url_path_for("delete_user"), headers=get_auth_headers(token_service, user))
    response.raise_for_status()

    deleted_user = user_service.get_user(user.username, active_only=False)
    assert not deleted_user
