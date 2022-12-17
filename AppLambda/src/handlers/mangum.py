import json

from mangum.handlers.utils import (
    handle_base64_response_body,
    handle_multi_value_headers,
)
from mangum.types import LambdaConfig, LambdaContext, LambdaEvent, Response, Scope


class SQS:
    """
    Custom SQS event handler for Mangum

    Hijacks all requests with a "Records" key in them and emulates a POST request to the provided path.
    Must pass to Mangum using the `set_path` class method
    """

    path = ""

    @classmethod
    def with_path(cls, path: str):
        cls.path = path
        return cls

    @classmethod
    def infer(cls, event: LambdaEvent, context: LambdaContext, config: LambdaConfig) -> bool:
        return "Records" in event and cls.path  # type: ignore

    def __init__(self, event: LambdaEvent, context: LambdaContext, config: LambdaConfig) -> None:
        self.event = event
        self.context = context
        self.config = config

    @property
    def body(self) -> bytes:
        return json.dumps(self.event).encode()

    @property
    def scope(self) -> Scope:
        headers: dict[str, str] = {}
        return {
            "type": "http",
            "method": "POST",
            "http_version": "1.1",
            "headers": [[k.encode(), v.encode()] for k, v in headers.items()],
            "path": self.path,
            "raw_path": None,
            "root_path": "",
            "scheme": headers.get("x-forwarded-proto", "https"),
            "query_string": "",
            "server": None,
            "client": None,
            "asgi": {"version": "3.0", "spec_version": "2.0"},
            "aws.event": self.event,
            "aws.context": self.context,
        }

    def __call__(self, response: Response) -> dict:
        finalized_headers, multi_value_headers = handle_multi_value_headers(response["headers"])
        finalized_body, is_base64_encoded = handle_base64_response_body(
            response["body"], finalized_headers
        )

        return {
            "statusCode": response["status"],
            "headers": finalized_headers,
            "multiValueHeaders": multi_value_headers,
            "body": finalized_body,
            "isBase64Encoded": is_base64_encoded,
        }
