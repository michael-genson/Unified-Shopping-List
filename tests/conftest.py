from fastapi.testclient import TestClient
from pytest import MonkeyPatch, fixture

from AppLambda.src import config
from AppLambda.src.app import app, services
from AppLambda.src.clients import aws
from AppLambda.src.services.rate_limit import RateLimitService
from AppLambda.src.services.smtp import SMTPService

from .fixtures import *
from .mocks.database import DynamoDBMock


@fixture(scope="module", autouse=True)
def setup():
    config.USE_WHITELIST = False
    do_nothing = lambda *args, **kwargs: None
    mp = MonkeyPatch()

    mp.setattr(aws, "DynamoDB", DynamoDBMock)
    mp.setattr(SMTPService, "send", do_nothing)

    # rate limit service is flaky during testing, so we disable it by default
    mp.setattr(RateLimitService, "verify_rate_limit", do_nothing)
    yield


@fixture(autouse=True)
def function_teardown():
    yield
    services.reset()
    config.USE_WHITELIST = False  # TODO: use reset function


@fixture(scope="session")
def api_client():
    yield TestClient(app)
