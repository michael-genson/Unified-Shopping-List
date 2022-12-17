from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel
from todoist_api_python.models import Task

from ..models._base import APIBase
from ..models.core import BaseSyncEvent, Source

### Auth ###


class TodoistAuthRequest(BaseModel):
    client_id: str
    scope: str
    state: str


class TodoistRedirect(BaseModel):
    code: Optional[str] = None
    """always provided, unless there is an error"""

    state: Optional[str] = None
    """always provided, unless there is an error"""

    error: Optional[str] = None
    """if not null, something went wrong and both code and state will be null"""


class TodoistTokenExchangeRequest(BaseModel):
    client_id: str
    client_secret: str
    code: str


class TodoistTokenResponse(BaseModel):
    access_token: str
    token_type: str


### Tasks ###
class TodoistTask(APIBase):
    id: str
    project_id: str
    user_id: str
    is_completed: bool

    content: str
    description: str
    labels: list[str]
    order: int
    priority: int
    section_id: Optional[str]

    @classmethod
    def parse_api_task(cls, task: Task):
        return TodoistTask(user_id=task.creator_id, **task.to_dict())


### Sync ###
class TodoistEventType(Enum):
    invalid = "invalid"

    item_added = "item:added"
    item_updated = "item:updated"
    item_deleted = "item:deleted"
    item_completed = "item:completed"
    item_uncompleted = "item:uncompleted"

    @classmethod
    def _missing_(cls, value):
        return cls.invalid


class TodoistWebhook(BaseModel):
    version: str
    event_name: TodoistEventType
    user_id: str
    initiator: dict[str, Any]
    event_data: dict[str, Any]


class TodoistSyncEvent(BaseSyncEvent):
    source: Source = Source.todoist
    project_id: str
