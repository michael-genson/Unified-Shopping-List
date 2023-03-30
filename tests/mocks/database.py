from typing import Any, Optional, cast

from botocore.exceptions import ClientError

from AppLambda.src.clients.aws import DynamoDB, MissingPrimaryKeyError
from AppLambda.src.models.aws import DynamoDBAtomicOp


def _client_error(code: str, operation: str, message="Mock Client Error"):
    return ClientError({"Error": {"Code": code, "Message": message}}, operation)


class DynamoDBMock(DynamoDB):
    """Mock DynamoDB calls"""

    def __init__(self, tablename: str, primary_key: str) -> None:
        self._mock_db: dict[str, dict[str, Any]] = {}
        super().__init__(tablename, primary_key)

    def get(self, primary_key_value: str) -> Optional[dict[str, Any]]:
        return self._mock_db.get(primary_key_value)

    def query(self, key: str, value: str) -> list[dict[str, Any]]:
        items = []
        for row in self._mock_db.values():
            if row.get(key) == value:
                items.append(row)

        return items

    def put(self, item: dict[str, Any], allow_update=True) -> None:
        if self.pk not in item:
            raise MissingPrimaryKeyError(self.pk)

        if not allow_update:
            pk_value = item[self.pk]
            if pk_value in self._mock_db:
                # technically this should be a ConditionalCheckFailedException, not a ClientError,
                # but this would need to be constructed from botocore.errorfactory
                raise _client_error("ConditionalCheckFailedException", "PutItem", "pk already exists")

        self._mock_db[item[self.pk]] = item

    def atomic_op(
        self, primary_key_value: str, attribute: str, attribute_change_value: int, op: DynamoDBAtomicOp
    ) -> int:
        attr_components = attribute.split(".")
        data = self._mock_db.get(primary_key_value)
        if not data:
            raise _client_error("ValidationException", "UpdateItem", "pk value not in database")

        for component in attr_components:
            if component not in data:
                # raise client error
                break

            elif isinstance(data[component], int):
                if op == DynamoDBAtomicOp.overwrite:
                    data[component] = attribute_change_value
                    return attribute_change_value

                elif op == DynamoDBAtomicOp.increment:
                    data[component] += attribute_change_value
                    return data[component]

                elif op == DynamoDBAtomicOp.decrement:
                    data[component] -= attribute_change_value
                    return data[component]

            elif not isinstance(data[component], dict):
                # raise client error
                break

            else:
                # drill-down into nested data
                data = cast(dict[str, Any], data[component])

        raise _client_error("ValidationException", "UpdateItem", "malformed attribute")

    def delete(self, primary_key_value: str) -> None:
        self._mock_db.pop(primary_key_value, None)
