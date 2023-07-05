import json
from datetime import datetime
from enum import Enum
from json import JSONDecodeError
from typing import Any

from pydantic import BaseModel, ValidationError, validator
from requests import Response

from ..models.core import BaseSyncEvent, Source
from ._base import APIBase


class MealieBase(APIBase):
    @classmethod
    def parse_response(cls, response: Response):
        """parses a response or raises the appropriate exception"""

        try:
            return cls.parse_obj(response.json())

        # TODO: write a custom exception type
        except JSONDecodeError as e:
            raise Exception("invalid response received from Mealie (invalid JSON)") from e

        # TODO: write a custom exception type
        except ValidationError as e:
            raise Exception("invalid response format") from e


### Auth ###


class AuthToken(APIBase):
    token: str
    name: str
    id: str


### API ###


class Pagination(MealieBase):
    page: int = 1
    per_page: int = 10
    total: int = 0
    total_pages: int = 0
    items: list[dict]
    next: str | None
    previous: str | None


class MealieRecipe(MealieBase):
    """Subset of the Mealie Recipe schema"""

    id: str
    slug: str
    name: str | None = None

    def __str__(self) -> str:
        return self.name or ""


class Label(MealieBase):
    id: str
    name: str
    color: str

    def __str__(self) -> str:
        return self.name


class UnitFoodBase(MealieBase):
    name: str
    description: str = ""
    extras: dict | None = {}


class Unit(UnitFoodBase):
    id: str | None
    fraction: bool
    abbreviation: str
    use_abbreviation: bool | None

    def __str__(self) -> str:
        return self.abbreviation if self.use_abbreviation else self.name


class Food(UnitFoodBase):
    id: str | None
    label: Label | None = None

    def __str__(self) -> str:
        return self.name


class MealieShoppingListRecipeRef(MealieBase):
    recipe_id: str

    id: str | None
    shopping_list_id: str | None
    recipe_quantity: float | None = 0
    recipe: MealieRecipe | None


class MealieShoppingListItemRecipeRefCreate(MealieBase):
    recipe_id: str
    recipe_quantity: float = 0
    """the quantity of this item in a single recipe (scale == 1)"""

    recipe_scale: float | None = 1
    """the number of times this recipe has been added"""

    @validator("recipe_quantity", pre=True)
    def default_none_to_zero(cls, v):
        return 0 if v is None else v


class MealieShoppingListItemRecipeRefUpdate(MealieShoppingListItemRecipeRefCreate):
    id: str
    shopping_list_item_id: str


class MealieShoppingListItemRecipeRefOut(MealieShoppingListItemRecipeRefUpdate):
    ...


class MealieShoppingListItemExtras(MealieBase):
    original_value: str | None
    todoist_task_id: str | None

    alexa_item_id: str | None
    alexa_item_version: str | None
    """string representation of the Alexa list item's version number (int)"""


class MealieShoppingListItemBase(MealieBase):
    shopping_list_id: str
    checked: bool = False
    position: int = 0

    is_food: bool = False

    note: str | None = ""
    quantity: float = 1

    food_id: str | None = None
    label_id: str | None = None
    unit_id: str | None = None

    extras: MealieShoppingListItemExtras | None = None


class MealieShoppingListItemCreate(MealieShoppingListItemBase):
    recipe_references: list[MealieShoppingListItemRecipeRefCreate] = []


class MealieShoppingListItemUpdate(MealieShoppingListItemBase):
    recipe_references: list[MealieShoppingListItemRecipeRefCreate | MealieShoppingListItemRecipeRefUpdate] = []


class MealieShoppingListItemUpdateBulk(MealieShoppingListItemUpdate):
    """Only used for bulk update operations where the shopping list item id isn't already supplied"""

    id: str


class MealieShoppingListItemOut(MealieShoppingListItemBase):
    id: str
    display: str
    """
    How the ingredient should be displayed

    Automatically calculated after the object is created
    """

    food: Food | None
    label: Label | None
    unit: Unit | None
    recipe_references: list[MealieShoppingListItemRecipeRefOut] = []


class MealieShoppingListItemsCollectionOut(MealieBase):
    """Container for bulk shopping list item changes"""

    created_items: list[MealieShoppingListItemOut] = []
    updated_items: list[MealieShoppingListItemOut] = []
    deleted_items: list[MealieShoppingListItemOut] = []


class MealieShoppingListOut(MealieBase):
    id: str
    name: str
    extras: dict | None
    list_items: list[MealieShoppingListItemOut] = []
    recipe_references: list[MealieShoppingListRecipeRef] = []

    created_at: datetime | None
    update_at: datetime | None


class MealieEventNotifierOptions(MealieBase):
    shopping_list_updated: bool = True


class MealieEventNotifierCreate(MealieBase):
    name: str
    apprise_url: str


class MealieEventNotifierOut(MealieBase):
    id: str
    group_id: str
    name: str
    enabled: bool = True


class MealieEventNotifierUpdate(MealieEventNotifierOut):
    apprise_url: str | None = None
    options: MealieEventNotifierOptions


### Sync ###


class MealieEventType(Enum):
    invalid = "invalid"

    shopping_list_created = "shopping_list_created"
    shopping_list_updated = "shopping_list_updated"
    shopping_list_deleted = "shopping_list_deleted"

    @classmethod
    def _missing_(cls, value):
        return cls.invalid


class MealieEventOperation(Enum):
    info = "info"

    create = "create"
    update = "update"
    delete = "delete"


class MealieEventNotification(BaseModel):
    event_id: str
    timestamp: datetime
    version: str

    title: str
    message: str
    event_type: MealieEventType
    integration_id: str
    document_data: str
    """JSON-encoded string"""

    def get_shopping_list_id_from_document_data(self) -> str | None:
        try:
            # sometimes the JSON string gets URL encoded with +, so we filter those out
            parsed_data: dict[str, Any] = json.loads(self.document_data.replace("+", " "))
            shopping_list_id = parsed_data.get("shoppingListId")
            if shopping_list_id is None:
                return None
            else:
                return str(shopping_list_id)

        except JSONDecodeError:
            return None


class MealieSyncEvent(BaseSyncEvent):
    source: Source = Source.mealie
    shopping_list_id: str
