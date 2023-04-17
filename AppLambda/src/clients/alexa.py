import time
from json import JSONDecodeError
from typing import Any, Optional, cast
from uuid import uuid4

import requests
from pydantic import ValidationError
from requests import HTTPError, Response

from .. import config
from ..app_secrets import ALEXA_CLIENT_ID, ALEXA_CLIENT_SECRET
from ..clients import aws
from ..models.alexa import CallbackData, CallbackEvent, Message, MessageIn

LWA_URL = "https://api.amazon.com/auth/o2/token"
ALEXA_MESSAGE_API_URL = "https://api.amazonalexa.com/v1/skillmessages/users/{user_id}"

# TODO: make these inherit from a custom exception type
NO_RESPONSE_EXCEPTION = "Could not find a response from Alexa"
NO_RESPONSE_DATA_EXCEPTION = "Alexa returned a response, but there was no response data"


class ListManagerClient:
    """Manages low-level Alexa Skills API interaction"""

    def __init__(self, max_attempts: int = 3, rate_limit_throttle: int = 5) -> None:
        self.access_token: str
        self.expiration: float
        self._refresh_token()
        self._event_callback_db: Optional[aws.DynamoDB] = None

        self.max_attempts = max_attempts
        self.rate_limit_throttle = rate_limit_throttle

    @property
    def event_callback_db(self):
        if not self._event_callback_db:
            self._event_callback_db = aws.DynamoDB(config.EVENT_CALLBACK_TABLENAME, config.EVENT_CALLBACK_PK)

        return self._event_callback_db

    ### Base ###

    def _refresh_token(self) -> None:
        payload = {
            "grant_type": "client_credentials",
            "client_id": ALEXA_CLIENT_ID,
            "client_secret": ALEXA_CLIENT_SECRET,
            "scope": "alexa:skill_messaging",
        }

        r = requests.post(LWA_URL, json=payload)
        r.raise_for_status()

        try:
            response_json = r.json()

        except JSONDecodeError:
            print(r.content)
            raise Exception("Unable to obtain Alexa Skill Messaging API Token; invalid JSON response")

        if "access_token" not in response_json:
            print(response_json)
            raise Exception("Alexa Skill Messaging API Token missing from response")

        self.access_token = response_json["access_token"]
        self.expiration = time.time() + response_json["expires_in"]

    def _send_message(self, user_id: str, message: Message, max_attempts=3) -> None:
        url = ALEXA_MESSAGE_API_URL.format(user_id=user_id)
        headers = {"Authorization": f"Bearer {self.access_token}"}
        payload = {"data": message.dict()}

        attempts = 0
        while True:
            attempts += 1

            try:
                if time.time() >= self.expiration:
                    self._refresh_token()
                    headers = {"Authorization": f"Bearer {self.access_token}"}

                r = requests.post(url, headers=headers, json=payload)
                r.raise_for_status()
                break

            except HTTPError as e:
                if attempts >= max_attempts:
                    raise

                response: Response = e.response
                if response.status_code not in [429, 500] or attempts >= self.max_attempts:
                    raise

                # something went wrong, so we wait and try again
                time.sleep(self.rate_limit_throttle)
                continue

    def _poll_for_event_response(self, event_id: str, poll_frequency=0.5, timeout=20) -> dict[str, Any]:
        """Poll DynamoDB for a particular event response and returns the full JSON"""

        start_time = time.time()
        while True:
            event = self.event_callback_db.get(event_id)
            if event:
                return event

            if time.time() >= start_time + timeout:
                raise Exception("Timed out waiting for callback")

            # the event doesn't exist yet, so we keep polling
            time.sleep(poll_frequency)
            continue

    def call_api(self, user_id: str, message: MessageIn) -> Optional[list[dict[str, Any]]]:
        """Call the Alexa API and optionally wait for a response"""

        if not message.event_id:
            message.event_id = str(uuid4())

        event_message = cast(Message, message)
        self._send_message(user_id, event_message)

        if not message.send_callback_response:
            return None

        # fetch response from DynamoDB
        data = self._poll_for_event_response(event_message.event_id)
        response = CallbackEvent.parse_obj(data)
        if not response:
            raise Exception(NO_RESPONSE_EXCEPTION)

        # extract response data
        try:
            callback_data = CallbackData.parse_raw(response.data)
            callback_data.raise_for_status()
            return callback_data.data

        except (JSONDecodeError, ValidationError):
            raise Exception("Invalid callback response format")
