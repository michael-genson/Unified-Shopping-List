from __future__ import annotations

from abc import ABC, abstractproperty
from typing import Callable, ClassVar, Optional

from pydantic import BaseModel

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
    selected_mealie_list_id: Optional[str]


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

    use_foods: Optional[bool] = False
    overwrite_original_item_names: Optional[bool] = False
    confidence_threshold: float = 0.8


class UserMealieConfiguration(UserMealieConfigurationUpdate, UserConfigurationBase):
    base_url: str
    auth_token: str

    auth_token_id: str
    notifier_id: str
    security_hash: str
    """Unencrypted random hash to verify notifications"""

    @property
    def is_valid(self):
        return all([self.base_url, self.auth_token])


### Todoist ###


class UserTodoistConfigurationCreate(APIBase):
    access_token: str


@as_form
class UserTodoistConfigurationUpdate(APIBase):
    as_form: ClassVar[Callable[..., UserTodoistConfigurationUpdate]]

    map_labels_to_sections: Optional[bool] = False
    default_section_name: str = "Uncategorized"


class UserTodoistConfiguration(UserTodoistConfigurationCreate, UserTodoistConfigurationUpdate, UserConfigurationBase):
    @property
    def is_valid(self):
        return bool(self.access_token)
