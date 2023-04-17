import os

import boto3
import pytest
from moto import mock_dynamodb  # type: ignore

from AppLambda.src.app import settings, secrets
from AppLambda.src.clients.aws import _aws


def set_aws_credentials():
    os.environ["AWS_ACCESS_KEY_ID"] = "disabled"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "disabled"
    os.environ["AWS_SECURITY_TOKEN"] = "disabled"
    os.environ["AWS_SESSION_TOKEN"] = "disabled"
    os.environ["AWS_DEFAULT_REGION"] = secrets.aws_region


@pytest.fixture(autouse=True)
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
            TableName=settings.users_tablename,
            KeySchema=[{"AttributeName": settings.users_pk, "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": settings.users_pk, "AttributeType": "S"},
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
            TableName=settings.alexa_event_callback_tablename,
            KeySchema=[{"AttributeName": settings.alexa_event_callback_pk, "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": settings.alexa_event_callback_pk, "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield

    # reset AWS services during teardown
    _aws.reset()
