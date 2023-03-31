from fastapi.testclient import TestClient

from AppLambda.src.app import services
from AppLambda.src.models.core import User
from AppLambda.src.routes import core
from tests.utils import get_auth_headers


def test_delete_user(api_client: TestClient, user: User):
    response = api_client.post(core.router.url_path_for("delete_user"), headers=get_auth_headers(user))
    response.raise_for_status()

    deleted_user = services.user.get_user(user.username, active_only=False)
    assert not deleted_user
