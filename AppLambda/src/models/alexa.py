from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel

from ._base import APIBase

### Auth ###


class AlexaAuthRequest(BaseModel):
    client_id: str
    redirect_uri: str
    response_type: str
    scope: str
    state: str


### List Management ###


class ListState(Enum):
    active = "active"
    archived = "archived"


class ListItemState(Enum):
    active = "active"
    completed = "completed"


class Operation(Enum):
    create = "create"
    read = "read"
    read_all = "read_all"
    update = "update"
    delete = "delete"


class ObjectType(Enum):
    list = "list"
    list_item = "list_item"


class MessageRequest(BaseModel):
    operation: Operation
    object_type: ObjectType
    object_data: Optional[dict[str, Any]]

    metadata: Optional[dict[str, Any]]

    class Config:
        use_enum_values = True


class MessageIn(APIBase):
    source: str
    event_id: Optional[str]
    requests: list[MessageRequest]

    metadata: Optional[dict[str, Any]]
    send_callback_response: Optional[bool]


class Message(MessageIn):
    event_id: str


class CallbackEvent(APIBase):
    event_source: str
    event_id: str
    data: str
    """JSON string representation of CallbackData"""


class CallbackData(APIBase):
    success: bool
    detail: Optional[str]
    data: Optional[list[dict[str, Any]]]

    def raise_for_status(self):
        """Raise an exception if the API call was unsuccessful"""
        if self.success:
            return

        raise Exception(f"Callback Exception from Alexa: {self.detail or 'Unknown Error'}")


### List ###
class ReadList(APIBase):
    list_id: str
    name: str
    state: ListState = ListState.active


class AlexaReadListCollection(APIBase):
    lists: list[ReadList]


### List Item ###
class AlexaReadListItem(APIBase):
    list_id: str
    item_id: str
    value: str
    status: ListItemState

    class Config:
        use_enum_values = True


class AlexaReadListItemCollection(APIBase):
    list_items: list[AlexaReadListItem]
