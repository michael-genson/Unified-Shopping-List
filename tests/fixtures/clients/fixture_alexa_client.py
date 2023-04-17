import pytest

from AppLambda.src.clients.alexa import ListManagerClient


@pytest.fixture()
def alexa_client() -> ListManagerClient:
    return ListManagerClient()
