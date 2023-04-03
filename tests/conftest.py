import os

import boto3
from fastapi.testclient import TestClient
from moto import mock_dynamodb  # type: ignore
from pytest import MonkeyPatch, fixture

from AppLambda.src import config
from AppLambda.src.app import app, services
from AppLambda.src.app_secrets import AWS_REGION
from AppLambda.src.clients.aws import _aws
from AppLambda.src.services.smtp import SMTPService

from .fixtures import *

do_nothing = lambda *args, **kwargs: None


@fixture(scope="session", autouse=True)
def mock_services():
    mp = MonkeyPatch()
    mp.setattr(SMTPService, "send", do_nothing)
    yield


@fixture(scope="session")
def api_client():
    yield TestClient(app)


@fixture(autouse=True)
def reset_config():
    config.USE_WHITELIST = False


@fixture(autouse=True)
def reset_factories():
    services.reset()
    _aws.reset()


def set_aws_credentials():
    os.environ["AWS_ACCESS_KEY_ID"] = "disabled"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "disabled"
    os.environ["AWS_SECURITY_TOKEN"] = "disabled"
    os.environ["AWS_SESSION_TOKEN"] = "disabled"
    os.environ["AWS_DEFAULT_REGION"] = AWS_REGION  # TODO: remove secrets dependency


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
                    "IndexName": "alexa_user_id",
                    "KeySchema": [{"AttributeName": "alexa_user_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "KEYS_ONLY"},
                },
                {
                    "IndexName": "todoist_user_id",
                    "KeySchema": [{"AttributeName": "todoist_user_id", "KeyType": "HASH"}],
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
