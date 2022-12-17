import json
from typing import Any, Optional, Union

import boto3
from dynamodb_json import json_util as ddb_json  # type: ignore

from ..app_secrets import AWS_REGION

session = boto3.Session(region_name=AWS_REGION)

ddb = session.client("dynamodb")
secrets = session.client("secretsmanager")
sqs = session.resource("sqs")


class DynamoDB:
    """Provides higher-level functions to interact with DynamoDB"""

    def __init__(self, tablename: str) -> None:
        self.tablename = tablename

    def get(self, key: str, value: str) -> Optional[dict[str, Any]]:
        """Gets a single item by primary key"""

        data = ddb.get_item(TableName=self.tablename, Key={key: {"S": value}})
        if "Item" not in data:
            return None

        return ddb_json.loads(data["Item"])

    def query(self, key: str, value: str) -> list[dict[str, Any]]:
        """Queries by primary key or global secondary index and returns all items"""

        key_condition_expression = f"{key} = :{key}"
        expression_attribute_values = {f":{key}": {"S": value}}

        data = ddb.query(
            TableName=self.tablename,
            IndexName=key,
            KeyConditionExpression=key_condition_expression,
            ExpressionAttributeValues=expression_attribute_values,
        )

        if "Items" not in data:
            return []

        return ddb_json.loads(data["Items"])

    def put(self, item: dict[str, Any], allow_update=True) -> None:
        """Creates or updates a single item"""

        if allow_update:
            ddb.put_item(TableName=self.tablename, Item=ddb_json.dumps(item, as_dict=True))

        else:
            ddb.put_item(
                TableName=self.tablename,
                Item=ddb_json.dumps(item, as_dict=True),
                ConditionExpression="attribute_not_exists(username)",
            )

    def delete(self, key: str, value: str) -> None:
        """Deletes one item by primary key"""

        ddb.delete_item(TableName=self.tablename, Key={key: {"S": value}})
        return


class SecretsManager:
    @staticmethod
    def get_secrets(secret_id: str) -> dict[str, Any]:
        """Fetches secrets from AWS secrets manager"""

        response = secrets.get_secret_value(SecretId=secret_id)
        return json.loads(response["SecretString"])


class SQSFIFO:
    """Provides higher-level functions to interact with SQS FIFO queues"""

    def __init__(self, queue_url: str) -> None:
        self.queue = sqs.Queue(queue_url)

    def send_message(self, content: Union[dict, list], de_dupe_id: str, group_id: str) -> None:
        self.queue.send_message(
            MessageBody=json.dumps(content),
            MessageDeduplicationId=de_dupe_id,
            MessageGroupId=group_id,
        )
