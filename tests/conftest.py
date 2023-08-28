import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch


from AppLambda.src.app import app, settings
from AppLambda.src.services.smtp import SMTPService

from .fixtures import *


def do_nothing(*args, **kwargs):
    return None


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
    settings.debug = True
    settings.use_whitelist = False
