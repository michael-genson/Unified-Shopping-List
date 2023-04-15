from datetime import datetime
from enum import Enum
from typing import Any, Optional

from dateutil.parser import parse as parse_date
from pydantic import BaseModel, validator

from ._base import APIBase
from .core import BaseSyncEvent, Source

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
        use_enum_values = True  # TODO: disable this and replace .dict() with .json()


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


### List Item ###
class AlexaReadListItem(APIBase):
    list_id: str
    item_id: str


class AlexaListItemCreateIn(APIBase):
    value: str
    status: ListItemState = ListItemState.active

    class Config:
        use_enum_values = True  # TODO: disable this and replace .dict() with .json()


class AlexaListItemCreate(AlexaListItemCreateIn):
    list_id: str


class AlexaListItemUpdateIn(APIBase):
    value: str
    status: Optional[ListItemState] = None
    """If null, the state will read from Alexa"""


class AlexaListItemUpdateBulkIn(AlexaListItemUpdateIn):
    id: str


class AlexaListItemUpdate(AlexaListItemCreate):
    item_id: str
    status: ListItemState
    version: int
    """This is incremented every time the item is updated. When created, it is set to 1"""


class AlexaListItemOut(APIBase):
    id: str
    value: str
    status: ListItemState
    version: int
    """This is incremented every time the item is updated. When created, it is set to 1"""

    created_time: datetime
    updated_time: datetime

    class Config:
        use_enum_values = True  # TODO: disable this and replace .dict() with .json()

    @validator("created_time", "updated_time", pre=True)
    def parse_timestamp(cls, v) -> datetime:
        if isinstance(v, str):
            return parse_date(v)

        return v


class AlexaListItemCollectionOut(APIBase):
    list_id: str
    list_items: list[AlexaListItemOut]


### List ###
class AlexaReadList(APIBase):
    list_id: str
    state: ListState = ListState.active

    class Config:
        use_enum_values = True  # TODO: disable this and replace .dict() with .json()


class AlexaListOut(AlexaReadList):
    name: str
    version: int
    """This is incremented every time the item is updated. When created, it is set to 1"""

    items: Optional[list[AlexaListItemOut]]
    """Only populated when a single list is fetched"""


class AlexaListCollectionOut(APIBase):
    lists: list[AlexaListOut]


### Sync ###
class AlexaListEvent(APIBase):
    request_id: str
    timestamp: datetime

    operation: Operation
    object_type: ObjectType

    list_id: str
    list_item_ids: Optional[list[str]] = []
    """only populated in list item events"""

    class Config:
        use_enum_values = True  # TODO: disable this and replace .dict() with .json()


class AlexaSyncEvent(BaseSyncEvent):
    source: Source = Source.alexa
    list_event: AlexaListEvent
