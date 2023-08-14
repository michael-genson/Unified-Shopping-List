import json
from datetime import datetime
from typing import Any, TypeVar
from uuid import uuid4

from fastapi.encoders import jsonable_encoder

from AppLambda.src.app import settings
from AppLambda.src.clients import aws
from AppLambda.src.models.alexa import (
    AlexaListItemCreate,
    AlexaListItemOut,
    AlexaListItemUpdate,
    CallbackData,
    CallbackEvent,
    Message,
    ObjectType,
    Operation,
)

T = TypeVar("T")


class ServiceException(Exception):
    """Generic Alexa Service Exception"""

    ...


class MockAlexaServer:
    def __init__(self) -> None:
        self.db: dict[str, dict[str, Any]] = {}
        self._ddb_client: aws.DynamoDB | None = None

    @classmethod
    def _assert(cls, data: T | None) -> T:
        if not data:
            raise ServiceException("data cannot be empty")

        return data

    @property
    def ddb_client(self):
        if not self._ddb_client:
            self._ddb_client = aws.DynamoDB(settings.alexa_event_callback_tablename, settings.alexa_event_callback_pk)

        return self._ddb_client

    def _get_list(self, request_data: dict[str, Any] | None) -> dict[str, Any]:
        request_data = self._assert(request_data)
        list_id: str = self._assert(request_data.get("list_id"))
        list_state: str = self._assert(request_data.get("state"))

        data = self.db.get(list_id)
        if data and data.get("state") != list_state:
            data = None

        return self._assert(data)

    def _get_all_lists(self) -> list[dict[str, Any]]:
        data = list(self.db.values())

        # when fetching all lists, items are not returned
        for alexa_list in data:
            alexa_list["items"] = None

        return data

    def _get_list_item(self, request_data: dict[str, Any] | None) -> dict[str, Any]:
        request_data = self._assert(request_data)
        list_id: str = self._assert(request_data.get("list_id"))
        item_id: str = self._assert(request_data.get("item_id"))

        list_data = self.db.get(list_id, {})
        items_data = list_data.get("items", [])
        assert isinstance(items_data, list)

        item_data: dict[str, Any] | None = None
        for item in items_data:
            if not isinstance(item, dict):
                continue

            if item.get("id") == item_id:
                item_data = item
                break

        return self._assert(item_data)

    def _create_list_item(self, request_data: dict[str, Any] | None) -> dict[str, Any]:
        create_list_item = AlexaListItemCreate.parse_obj(self._assert(request_data))
        new_list_item = create_list_item.cast(
            AlexaListItemOut, id=str(uuid4()), version=1, created_time=datetime.utcnow(), updated_time=datetime.utcnow()
        )

        new_list_item_data = new_list_item.dict()
        self._assert(self.db.get(create_list_item.list_id)).get("items", []).append(new_list_item_data)
        return new_list_item_data

    def _update_list_item(self, request_data: dict[str, Any] | None) -> dict[str, Any]:
        update_list_item = AlexaListItemUpdate.parse_obj(self._assert(request_data))

        existing_item_data: dict[str, Any] | None = None
        existing_item_index: int = -1
        for i, item in enumerate(self.db.get(update_list_item.list_id, {}).get("items", [])):
            if item.get("id") == update_list_item.item_id:
                existing_item_data = item
                existing_item_index = i
                break

        self._assert(existing_item_data)
        new_item = AlexaListItemOut.parse_obj(existing_item_data)

        self._assert(update_list_item.version == new_item.version)  # the Alexa API requires this
        new_item.value = update_list_item.value
        new_item.status = update_list_item.status
        new_item.version += 1

        # save changes
        new_item_data = new_item.dict()
        self.db[update_list_item.list_id]["items"][existing_item_index] = new_item_data
        return new_item_data

    def get_all_lists(self) -> list[dict[str, Any]]:
        """
        Fetch all lists

        Bypasses normal mock validation
        """

        return list(self.db.values())

    def get_list_by_id(self, list_id: str) -> dict[str, Any] | None:
        """
        Fetch a single list by id, if it exists

        Bypasses normal mock validation
        """

        return self.db.get(list_id)

    def send_message(self, user_id: str, message: Message, *args, **kwargs) -> None:
        # default response if there is no operation + object_type match
        response_body: CallbackData = CallbackData(success=False, detail="invalid operation + object_type parameters")
        try:
            responses: list[dict[str, Any]] = []
            for request in message.requests:
                response: dict[str, Any] | None = None

                if request.operation == Operation.read_all.value:
                    if request.object_type == ObjectType.list.value:
                        response = {"lists": self._get_all_lists()}

                elif request.operation == Operation.read.value:
                    if request.object_type == ObjectType.list.value:
                        response = self._get_list(request.object_data)

                    elif request.object_type == ObjectType.list_item.value:
                        response = self._get_list_item(request.object_data)

                else:
                    if request.object_type == ObjectType.list.value:
                        raise NotImplementedError()

                    elif request.object_type == ObjectType.list_item.value:
                        if request.operation == Operation.create.value:
                            response = self._create_list_item(request.object_data)

                        elif request.operation == Operation.update.value:
                            response = self._update_list_item(request.object_data)

                        elif request.operation == Operation.delete.value:
                            raise NotImplementedError()

                if response is not None:
                    response["metadata"] = request.metadata
                    responses.append(response)

        except NotImplementedError:
            raise

        except ServiceException:
            response_body = CallbackData(
                success=False,
                detail="Alexa service exception; are the provided object ids accurate?",
            )

        else:
            response_body = CallbackData(
                success=True,
                data=responses,
            )

        if not message.send_callback_response:
            return

        callback = CallbackEvent(
            event_source=message.source,
            event_id=message.event_id,
            data=json.dumps(jsonable_encoder(response_body.dict(exclude_none=True))),
        )

        self.ddb_client.put(callback.dict(exclude_none=True), allow_update=False)
