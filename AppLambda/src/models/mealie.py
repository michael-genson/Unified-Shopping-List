import json
from datetime import datetime
from enum import Enum
from fractions import Fraction
from json import JSONDecodeError
from typing import Any

from pydantic import BaseModel, ValidationError, validator
from requests import Response

from ..models.core import BaseSyncEvent, Source
from ._base import APIBase

INGREDIENT_QTY_PRECISION = 3
MAX_INGREDIENT_DENOMINATOR = 32

SUPERSCRIPT = dict(zip("1234567890", "¹²³⁴⁵⁶⁷⁸⁹⁰", strict=False))
SUBSCRIPT = dict(zip("1234567890", "₁₂₃₄₅₆₇₈₉₀", strict=False))


def display_fraction(fraction: Fraction):
    return (
        "".join([SUPERSCRIPT[c] for c in str(fraction.numerator)])
        + "/"
        + "".join([SUBSCRIPT[c] for c in str(fraction.denominator)])
    )


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
    plural_name: str | None = None
    description: str = ""
    extras: dict | None = {}


class Unit(UnitFoodBase):
    id: str | None
    fraction: bool
    abbreviation: str
    plural_abbreviation: str | None = ""
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
    position: int | None = None

    disable_amount: bool | None = None
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
    position: int
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
    position: int
    recipe_references: list[MealieShoppingListItemRecipeRefOut] = []

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # calculate missing is_food and disable_amount values
        # we can't do this in a validator since they depend on each other
        if self.is_food is None and self.disable_amount is not None:
            self.is_food = not self.disable_amount
        elif self.disable_amount is None and self.is_food is not None:
            self.disable_amount = not self.is_food
        elif self.is_food is None and self.disable_amount is None:
            self.is_food = bool(self.food)
            self.disable_amount = not self.is_food

        # format the display property, if Mealie doesn't give us one
        if not self.display:
            self.display = self._format_display()

    def _format_quantity_for_display(self) -> str:
        """How the quantity should be displayed"""

        qty: float | Fraction

        # decimal
        if not self.unit or not self.unit.fraction:
            qty = round(self.quantity or 0, INGREDIENT_QTY_PRECISION)
            if qty.is_integer():
                return str(int(qty))

            else:
                return str(qty)

        # fraction
        qty = Fraction(self.quantity or 0).limit_denominator(MAX_INGREDIENT_DENOMINATOR)
        if qty.denominator == 1:
            return str(qty.numerator)

        if qty.numerator <= qty.denominator:
            return display_fraction(qty)

        # convert an improper fraction into a mixed fraction (e.g. 11/4 --> 2 3/4)
        whole_number = 0
        while qty.numerator > qty.denominator:
            whole_number += 1
            qty -= 1

        return f"{whole_number} {display_fraction(qty)}"

    def _format_unit_for_display(self) -> str:
        if not self.unit:
            return ""

        use_plural = self.quantity and self.quantity > 1
        unit_val = ""
        if self.unit.use_abbreviation:
            if use_plural:
                unit_val = self.unit.plural_abbreviation or self.unit.abbreviation
            else:
                unit_val = self.unit.abbreviation

        if not unit_val:
            if use_plural:
                unit_val = self.unit.plural_name or self.unit.name
            else:
                unit_val = self.unit.name

        return unit_val

    def _format_food_for_display(self) -> str:
        if not self.food:
            return ""

        use_plural = (not self.quantity) or self.quantity > 1
        if use_plural:
            return self.food.plural_name or self.food.name
        else:
            return self.food.name

    def _format_display(self) -> str:
        components = []

        use_food = True
        if self.is_food is False:
            use_food = False
        elif self.disable_amount is True:
            use_food = False

        # ingredients with no food come across with a qty of 1, which looks weird
        # e.g. "1 2 tbsp of olive oil"
        if self.quantity and (use_food or self.quantity != 1):
            components.append(self._format_quantity_for_display())

        if not use_food:
            components.append(self.note or "")
        else:
            if self.quantity and self.unit:
                components.append(self._format_unit_for_display())

            if self.food:
                components.append(self._format_food_for_display())

            if self.note:
                components.append(self.note)

        return " ".join(components).strip()


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
