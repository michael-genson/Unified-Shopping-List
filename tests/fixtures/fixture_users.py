from fastapi.testclient import TestClient
from pytest import fixture

from AppLambda.src.models.core import User

from ..utils import create_user_with_known_credentials


@fixture()
def user(api_client: TestClient) -> User:
    user, _ = create_user_with_known_credentials(api_client)
    return user.cast(User)
