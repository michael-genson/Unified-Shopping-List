import json
from datetime import datetime
from enum import Enum
from fractions import Fraction
from json import JSONDecodeError
from typing import Any, Optional, Union

from pydantic import BaseModel, ValidationError
from requests import Response

from ..config import (
    MEALIE_UNIT_DECIMAL_PRECISION,
    MEALIE_UNIT_FRACTION_ALLOW_IMPROPER,
    MEALIE_UNIT_FRACTION_MAX_DENOMINATOR,
)
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
    next: Optional[str]
    previous: Optional[str]


class MealieRecipe(MealieBase):
    """Subset of the Mealie Recipe schema"""

    id: str
    slug: str
    name: Optional[str] = None

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
    extras: Optional[dict] = {}


class Unit(UnitFoodBase):
    id: Optional[str]
    fraction: bool
    abbreviation: str
    use_abbreviation: Optional[bool]

    def __str__(self) -> str:
        return self.abbreviation if self.use_abbreviation else self.name


class Food(UnitFoodBase):
    id: Optional[str]
    label: Optional[Label] = None

    def __str__(self) -> str:
        return self.name


class MealieShoppingListItemRecipeRef(MealieBase):
    recipe_id: str

    id: Optional[str]
    shopping_list_item_id: Optional[str]
    recipe_quantity: Optional[float] = 0


class MealieShoppingListItemExtras(MealieBase):
    original_value: Optional[str]
    alexa_item_id: Optional[str]
    todoist_task_id: Optional[str]


class MealieShoppingListItemCreate(MealieBase):
    shopping_list_id: str
    checked: bool = False
    position: int = 0

    is_food: bool = False

    note: Optional[str] = ""
    quantity: float = 1

    unit_id: Optional[str] = None
    food_id: Optional[str] = None
    label_id: Optional[str] = None

    recipe_references: list[MealieShoppingListItemRecipeRef] = []
    extras: Optional[MealieShoppingListItemExtras]


class MealieShoppingListItemUpdate(MealieShoppingListItemCreate):
    id: str


class MealieShoppingListItemOut(MealieShoppingListItemUpdate):
    unit: Optional[Unit]
    food: Optional[Food]
    label: Optional[Label]

    def _format_quantity(self) -> str:
        qty: Union[float, Fraction]

        # decimal
        if not self.unit or not self.unit.fraction:
            qty = round(self.quantity, MEALIE_UNIT_DECIMAL_PRECISION)
            if qty.is_integer():
                return str(int(qty))

            else:
                return str(qty)

        # fraction
        qty = Fraction(self.quantity).limit_denominator(MEALIE_UNIT_FRACTION_MAX_DENOMINATOR)
        if qty.denominator == 1:
            return str(qty.numerator)

        if qty.numerator <= qty.denominator or MEALIE_UNIT_FRACTION_ALLOW_IMPROPER:
            return str(qty)

        # convert an improper fraction into a mixed fraction (e.g. 11/4 --> 2 3/4)
        whole_number = 0
        while qty.numerator > qty.denominator:
            whole_number += 1
            qty -= 1

        return f"{whole_number} {qty}"

    @property
    def display(self) -> str:
        components = []

        # ingredients with no food come across with a qty of 1, which looks weird
        # e.g. "1 2 tbsp of olive oil"
        if self.quantity and (self.is_food or self.quantity != 1):
            components.append(self._format_quantity())

        if not self.is_food:
            components.append(self.note or "")

        else:
            if self.quantity and self.unit:
                components.append(str(self.unit))

            if self.food:
                components.append(str(self.food))

            if self.note:
                if self.food and self.note[0] != "(" and self.note[-1] != ")":
                    components.append(f"({self.note})")

                else:
                    components.append(str(self.note))

        return " ".join(components)


class MealieShoppingListOut(MealieBase):
    id: str
    name: str
    extras: Optional[dict]
    list_items: list[MealieShoppingListItemOut] = []

    created_at: Optional[datetime]
    update_at: Optional[datetime]


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
    apprise_url: Optional[str] = None
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

    def get_shopping_list_id_from_document_data(self) -> Optional[str]:
        try:
            # sometimes the JSON string gets URL encoded with +, so we filter those out
            parsed_data: dict[str, Any] = json.loads(self.document_data.replace("+", " "))
            return str(parsed_data.get("shoppingListId"))

        except JSONDecodeError:
            return None


class MealieSyncEvent(BaseSyncEvent):
    source: Source = Source.mealie
    shopping_list_id: str
