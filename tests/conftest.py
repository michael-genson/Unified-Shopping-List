import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from AppLambda.src import config
from AppLambda.src.app import app
from AppLambda.src.services.smtp import SMTPService

from .fixtures import *

do_nothing = lambda *args, **kwargs: None


@pytest.fixture(scope="session", autouse=True)
def mock_services():
    mp = MonkeyPatch()
    mp.setattr(SMTPService, "send", do_nothing)
    yield


@pytest.fixture(scope="session")
def api_client():
    yield TestClient(app)


@pytest.fixture(autouse=True)
def reset_config():
    config.USE_WHITELIST = False
