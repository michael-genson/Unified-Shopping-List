import os

import boto3
from fastapi.testclient import TestClient
from moto import mock_dynamodb  # type: ignore
from pytest import MonkeyPatch, fixture

from AppLambda.src import config
from AppLambda.src.app import app, services
from AppLambda.src.app_secrets import AWS_REGION
from AppLambda.src.clients.aws import _aws
from AppLambda.src.services.rate_limit import RateLimitService
from AppLambda.src.services.smtp import SMTPService

from .fixtures import *

do_nothing = lambda *args, **kwargs: None


def set_aws_credentials():
    os.environ["AWS_ACCESS_KEY_ID"] = "disabled"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "disabled"
    os.environ["AWS_SECURITY_TOKEN"] = "disabled"
    os.environ["AWS_SESSION_TOKEN"] = "disabled"
    os.environ["AWS_DEFAULT_REGION"] = AWS_REGION  # TODO: remove secrets dependency


def mock_services(mp: MonkeyPatch):
    mp.setattr(SMTPService, "send", do_nothing)

    # rate limit service is flaky during testing, so we disable it by default
    mp.setattr(RateLimitService, "verify_rate_limit", do_nothing)


def patch_config():
    config.USE_WHITELIST = False


@fixture(scope="module", autouse=True)
def setup():
    set_aws_credentials()
    mp = MonkeyPatch()

    mock_services(mp)
    patch_config()
    yield


@fixture(autouse=True)
def function_teardown():
    yield
    # reset factories for every test
    services.reset()
    _aws.reset()


@fixture(autouse=True)
def inject_mock_database():
    """Create mock DynamoDB tables and inject the mock client into the client service factory"""

    set_aws_credentials()
    with mock_dynamodb():
        # inject client
        from moto.core import patch_client  # type: ignore

        patch_client(_aws.ddb)
        # set up tables
        ddb_resource = boto3.resource("dynamodb")
        ddb_resource.create_table(
            TableName=config.USERS_TABLENAME,
            KeySchema=[{"AttributeName": config.USERS_PK, "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": config.USERS_PK, "AttributeType": "S"},
                {"AttributeName": "alexa_user_id", "AttributeType": "S"},
                {"AttributeName": "todoist_user_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "idx1",
                    "KeySchema": [{"AttributeName": "alexa_user_id", "KeyType": "Hash"}],
                    "Projection": {"ProjectionType": "KEYS_ONLY"},
                },
                {
                    "IndexName": "idx2",
                    "KeySchema": [{"AttributeName": "todoist_user_id", "KeyType": "Hash"}],
                    "Projection": {"ProjectionType": "KEYS_ONLY"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        ddb_resource.create_table(
            TableName=config.EVENT_CALLBACK_TABLENAME,
            KeySchema=[{"AttributeName": config.EVENT_CALLBACK_PK, "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": config.EVENT_CALLBACK_PK, "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


@fixture(scope="session")
def api_client():
    yield TestClient(app)
