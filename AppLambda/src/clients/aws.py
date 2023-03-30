import json
import logging
from typing import Any, Optional, Union, cast

import boto3
from dynamodb_json import json_util as ddb_json  # type: ignore

from ..app_secrets import AWS_REGION
from ..models.aws import DynamoDBAtomicOp

session = boto3.Session(region_name=AWS_REGION)

ddb = session.client("dynamodb")
secrets = session.client("secretsmanager")
sqs = session.resource("sqs")


class MissingPrimaryKeyError(ValueError):
    def __init__(self, primary_key: str) -> None:
        super().__init__(f'item is missing the primary key "{primary_key}"')


class DynamoDB:
    """Provides higher-level functions to interact with DynamoDB"""

    def __init__(self, tablename: str, primary_key: str) -> None:
        self.tablename = tablename
        self.pk = primary_key

    def get(self, primary_key_value: str) -> Optional[dict[str, Any]]:
        """Gets a single item by primary key"""

        data = ddb.get_item(TableName=self.tablename, Key={self.pk: {"S": primary_key_value}})
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

        if self.pk not in item:
            raise MissingPrimaryKeyError(self.pk)

        if allow_update:
            ddb.put_item(TableName=self.tablename, Item=ddb_json.dumps(item, as_dict=True))

        else:
            ddb.put_item(
                TableName=self.tablename,
                Item=ddb_json.dumps(item, as_dict=True),
                ConditionExpression=f"attribute_not_exists({self.pk})",
            )

    def atomic_op(
        self, primary_key_value: str, attribute: str, attribute_change_value: int, op: DynamoDBAtomicOp
    ) -> int:
        """Performs an atomic operation"""

        # nested attributes are separated by dots, so we need to break them out and parameterize them
        attr_components = attribute.split(".")
        ex_attribute_names = {f"#attribute{i}": attr for i, attr in enumerate(attr_components)}
        ex_attribute_values = {":dif": {"N": str(attribute_change_value)}}

        # ex: "counters.likes = 0"
        if op == DynamoDBAtomicOp.overwrite:
            ex_equals = ":dif"

        # ex: "counters.likes = counters.likes + 1"
        else:
            ex_equals = f"{'.'.join(ex_attribute_names)} {op.value} :dif"

        expression = f"SET {'.'.join(ex_attribute_names)} = {ex_equals}"

        response_data = ddb.update_item(
            TableName=self.tablename,
            Key={self.pk: {"S": primary_key_value}},
            ExpressionAttributeNames=ex_attribute_names,
            ExpressionAttributeValues=ex_attribute_values,
            UpdateExpression=expression,
            ReturnValues="UPDATED_NEW",
        )

        data: Union[dict, int] = ddb_json.loads(response_data["Attributes"])
        data = cast(dict, data)

        # we need to unpack the data to get the final nested key, so we recursively drill-down into the data
        for attr_component in attr_components:
            data = data.pop(attr_component)
            if isinstance(data, int):
                return data

        logging.error("Reached end of nested atomic op; this should never happen!")
        logging.error(f"Looking for value of: {attribute}")
        logging.error(f"Response: {response_data}")
        raise Exception("Invalid response from DynamoDB")

    def delete(self, primary_key_value: str) -> None:
        """Deletes one item by primary key"""

        ddb.delete_item(TableName=self.tablename, Key={self.pk: {"S": primary_key_value}})
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

    def send_message(self, content: str, de_dupe_id: str, group_id: str) -> None:
        self.queue.send_message(
            MessageBody=content,
            MessageDeduplicationId=de_dupe_id,
            MessageGroupId=group_id,
        )
