import pytest
from pytest import MonkeyPatch

from AppLambda.src.clients.alexa import ListManagerClient

from .router import MockAlexaServer

_mock_alexa_server = MockAlexaServer()


@pytest.fixture()
def alexa_server() -> MockAlexaServer:
    return _mock_alexa_server


@pytest.fixture(scope="session", autouse=True)
def mock_alexa_server():
    """Replace all Alexa API calls with locally mocked database calls"""

    mp = MonkeyPatch()
    mp.setattr(ListManagerClient, "_refresh_token", lambda *args, **kwargs: None)
    mp.setattr(
        ListManagerClient, "_send_message", lambda *args, **kwargs: _mock_alexa_server.send_message(*args, **kwargs)
    )
    yield


@pytest.fixture(autouse=True)
def clean_up_database():
    yield
    _mock_alexa_server.db.clear()
