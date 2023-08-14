import time
from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from ..app import secrets, settings
from ..clients import aws
from ._base import APIBase
from .account_linking import UserAlexaConfiguration, UserMealieConfiguration, UserTodoistConfiguration


class WhitelistError(Exception):
    def __init__(self):
        super().__init__("You are not whitelisted on this application")


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
    alexa_list_id: str | None
    todoist_project_id: str | None


class UserConfiguration(APIBase):
    alexa: UserAlexaConfiguration | None
    mealie: UserMealieConfiguration | None
    todoist: UserTodoistConfiguration | None


class UserRateLimit(APIBase):
    value: int
    expires: int


class User(APIBase):
    username: str
    email: str
    disabled: bool

    user_expires: int | None = None
    last_registration_token: str | None = None
    last_password_reset_token: str | None = None
    incorrect_login_attempts: int | None = 0

    is_rate_limit_exempt: bool | None = False  # TODO: migrate and make this required
    rate_limit_map: dict[str, UserRateLimit] | None = {}  # TODO: migrate and make this required
    """Map of `RateLimitCategory` to `UserRateLimit`"""

    configuration: UserConfiguration = UserConfiguration()
    list_sync_maps: dict[str, ListSyncMap] = {}
    """Map of `mealie_shopping_list_id` to `ListSyncMap`"""

    alexa_user_id: str | None = None
    todoist_user_id: str | None = None

    use_developer_routes: bool = False

    @property
    def is_linked_to_mealie(self):
        return bool(self.configuration.mealie and self.configuration.mealie.is_valid)

    @property
    def is_linked_to_alexa(self):
        return bool(self.alexa_user_id and self.configuration.alexa and self.configuration.alexa.is_valid)

    @property
    def is_linked_to_todoist(self):
        return bool(self.todoist_user_id and self.configuration.todoist and self.configuration.todoist.is_valid)

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

    client_id = secrets.app_client_id
    client_secret = secrets.app_client_secret

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True  # TODO: disable this and replace .dict() with .json()

    @property
    def group_id(self):
        return self.username  # preserves order of events per-user

    def send_to_queue(self, use_dev_route=False) -> None:
        """Queue this event to be processed asynchronously"""

        sqs = aws.SQSFIFO(
            settings.sync_event_dev_sqs_queue_name if use_dev_route else settings.sync_event_sqs_queue_name
        )
        sqs.send_message(self.json(), self.event_id, self.group_id)
