from typing import Optional
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from AppLambda.src import config
from AppLambda.src.app import app
from AppLambda.src.clients import aws
from AppLambda.src.models.aws import SQSMessage
from AppLambda.src.routes import event_handlers
from tests.utils.generators import random_string


class MockSQSFIFO:
    def __init__(self, queue_url: str, *args, **kwargs) -> None:
        self.queue_url = queue_url
        self.api_client = TestClient(app)

    def _build_message(self, content: str) -> SQSMessage:
        return SQSMessage(
            message_id=str(uuid4()), receipt_handle=random_string(), body=content, attributes={}, message_attributes={}
        )

    def send_message(self, content: str, *args, **kwargs) -> None:
        if self.queue_url == config.SYNC_EVENT_DEV_SQS_QUEUE_NAME or config.SYNC_EVENT_SQS_QUEUE_NAME:
            self.api_client.post(
                event_handlers.router.url_path_for("sqs_sync_event_handler"), json=[self._build_message(content).dict()]
            )
        else:
            raise NotImplementedError(f"unsupported queue url {self.queue_url}")


@pytest.fixture(scope="session", autouse=True)
def mock_sqs_fifo_client():
    mp = MonkeyPatch()
    mp.setattr(aws, "SQSFIFO", MockSQSFIFO)
    yield
