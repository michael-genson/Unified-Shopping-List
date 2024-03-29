from __future__ import annotations

from abc import ABC, abstractproperty
from typing import Callable, ClassVar

from pydantic import BaseModel, validator

from ._base import APIBase, as_form


class NotLinkedError(Exception):
    def __init__(self, username: str, system: str):
        super().__init__(f"{username} is not linked to {system}")


### Base ###


class UserConfigurationBase(ABC, APIBase):
    @abstractproperty
    def is_valid(self) -> bool:
        pass


class SyncMapRender(BaseModel):
    list_id: str
    list_name: str
    selected_mealie_list_id: str | None


class SyncMapRenderList(BaseModel):
    column_header: str
    is_unidirectional: bool = False
    lists: list[SyncMapRender]


### Alexa ###
class UserAlexaConfigurationCreate(APIBase):
    user_id: str


class UserAlexaConfiguration(UserConfigurationBase):
    @property
    def is_valid(self):
        return True


### Mealie ###


@as_form
class UserMealieConfigurationCreate(APIBase):
    as_form: ClassVar[Callable[..., UserMealieConfigurationCreate]]

    base_url: str
    initial_auth_token: str
    """Used for creating a new auth token on behalf of the user"""


@as_form
class UserMealieConfigurationUpdate(APIBase):
    as_form: ClassVar[Callable[..., UserMealieConfigurationCreate]]

    use_foods: bool | None = False
    overwrite_original_item_names: bool | None = False
    confidence_threshold: float = 0.8


class UserMealieConfiguration(UserMealieConfigurationUpdate, UserConfigurationBase):
    base_url: str
    auth_token: str

    auth_token_id: str
    notifier_id: str
    security_hash: str
    """Unencrypted random hash to verify notifications"""

    @validator("base_url")
    def validate_base_url(cls, v: str):
        if not v:
            raise ValueError("base_url must not be empty")

        if v[-1] != "/":
            v += "/"

        if "http" not in v:
            v = "https://" + v

        return v

    @property
    def is_valid(self):
        return all([self.base_url, self.auth_token])


### Todoist ###


class UserTodoistConfigurationCreate(APIBase):
    access_token: str


@as_form
class UserTodoistConfigurationUpdate(APIBase):
    as_form: ClassVar[Callable[..., UserTodoistConfigurationUpdate]]

    map_labels_to_sections: bool | None = False
    default_section_name: str = "Uncategorized"

    add_recipes_to_task_description: bool | None = False


class UserTodoistConfiguration(UserTodoistConfigurationCreate, UserTodoistConfigurationUpdate, UserConfigurationBase):
    @property
    def is_valid(self):
        return bool(self.access_token)
