import time
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from ..app_secrets import APP_CLIENT_ID, APP_CLIENT_SECRET, SYNC_FIFO_QUEUE_NAME
from ..clients.aws import SQSFIFO
from ._base import APIBase
from .account_linking import (
    UserAlexaConfiguration,
    UserMealieConfiguration,
    UserTodoistConfiguration,
)


class Token(BaseModel):
    access_token: str
    token_type: str


class RateLimitCategory(Enum):
    read = "read"
    modify = "modify"
    sync = "sync"


class RateLimitInterval(Enum):
    minutely = "minutely"


class ListSyncMap(APIBase):
    """A collection of shopping lists to keep in sync"""

    mealie_shopping_list_id: str
    alexa_list_id: Optional[str]
    todoist_project_id: Optional[str]


class UserConfiguration(APIBase):
    alexa: Optional[UserAlexaConfiguration]
    mealie: Optional[UserMealieConfiguration]
    todoist: Optional[UserTodoistConfiguration]


class UserRateLimit(APIBase):
    value: int
    expires: int


class User(APIBase):
    username: str
    email: str
    disabled: bool

    user_expires: Optional[int] = None
    last_registration_token: Optional[str] = None
    last_password_reset_token: Optional[str] = None
    incorrect_login_attempts: Optional[int] = 0

    is_rate_limit_exempt: Optional[bool] = False
    rate_limit_map: Optional[dict[str, UserRateLimit]] = {}
    """Key is the rate limit category"""

    configuration: UserConfiguration = UserConfiguration()
    list_sync_maps: dict[str, ListSyncMap] = {}
    """Key is the Mealie shopping list id"""

    alexa_user_id: Optional[str] = None
    todoist_user_id: Optional[str] = None

    @property
    def is_linked_to_mealie(self):
        return self.configuration.mealie and self.configuration.mealie.is_valid

    @property
    def is_linked_to_alexa(self):
        return (
            self.alexa_user_id and self.configuration.alexa and self.configuration.alexa.is_valid
        )

    @property
    def is_linked_to_todoist(self):
        return (
            self.todoist_user_id
            and self.configuration.todoist
            and self.configuration.todoist.is_valid
        )

    def set_expiration(self, expiration_in_seconds: int) -> int:
        """Sets expiration time in seconds and returns the TTL value"""

        self.user_expires = round(time.time()) + expiration_in_seconds
        return self.user_expires


class UserInDB(User):
    hashed_password: str


class Source(Enum):
    alexa = "Alexa"
    mealie = "Mealie"
    todoist = "Todoist"


class BaseSyncEvent(APIBase):
    username: str
    source: Source

    client_id = APP_CLIENT_ID
    client_secret = APP_CLIENT_SECRET
    event_id: str = Field(default_factory=lambda: str(uuid4()))

    class Config:
        use_enum_values = True

    @property
    def group_id(self):
        return self.username  # preserves order of events per-user

    def send_to_queue(self) -> None:
        """Queue this event to be processed asynchronously"""

        sqs = SQSFIFO(SYNC_FIFO_QUEUE_NAME)
        sqs.send_message(self.dict(), self.event_id, self.group_id)
