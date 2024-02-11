import pytest
from AppLambda.src.models.mealie import Food, MealieShoppingListItemOut, Unit
from tests.utils.generators import random_bool, random_string, random_int


@pytest.mark.parametrize("use_fraction", [True, False])
@pytest.mark.parametrize("use_food", [True, False])
def test_mealie_shopping_list_generates_missing_display(use_fraction: bool, use_food: bool):
    food = Food(name=random_string())
    unit = Unit(name=random_string(), fraction=use_fraction, abbreviation=random_string(), use_abbreviation=False)
    list_item = MealieShoppingListItemOut(
        id=random_string(),
        display="",
        shopping_list_id=random_string(),
        checked=random_bool(),
        position=random_int(1, 100),
        disable_amount=None,
        is_food=use_food,
        note=random_string(),
        quantity=random_int(1, 100) + 0.5,
        food=food,
        unit=unit,
    )

    qty_display = (str(int(list_item.quantity)) + " ¹/₂") if use_fraction else str(list_item.quantity)
    if use_food:
        assert list_item.display == f"{qty_display} {unit.name} {food.name} {list_item.note}"
    else:
        assert list_item.display == f"{qty_display} {list_item.note}"


def test_mealie_shopping_list_not_overwrite_existing_display():
    food = Food(name=random_string())
    unit = Unit(name=random_string(), fraction=True, abbreviation=random_string(), use_abbreviation=False)
    display = random_string()
    list_item = MealieShoppingListItemOut(
        id=random_string(),
        display=display,
        shopping_list_id=random_string(),
        checked=random_bool(),
        position=random_int(1, 100),
        disable_amount=None,
        is_food=True,
        note=random_string(),
        quantity=random_int(1, 100) + 0.5,
        food=food,
        unit=unit,
    )

    assert list_item.display == display
