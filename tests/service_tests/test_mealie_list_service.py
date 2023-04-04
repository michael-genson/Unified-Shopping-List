import random
from typing import Callable, Optional

import pytest

from AppLambda.src.models.account_linking import NotLinkedError
from AppLambda.src.models.core import User
from AppLambda.src.models.mealie import (
    Food,
    Label,
    MealieRecipe,
    MealieShoppingListItemCreate,
    MealieShoppingListItemUpdateBulk,
    MealieShoppingListOut,
)
from AppLambda.src.services.mealie import MealieListService
from tests.utils import random_string


def test_mealie_list_service_unlinked_user(user: User):
    with pytest.raises(NotLinkedError):
        MealieListService(user)


def test_mealie_list_service_recipe_store(mealie_list_service: MealieListService, mealie_recipes: list[MealieRecipe]):
    for recipe in mealie_recipes:
        assert recipe.id in mealie_list_service.recipe_store
        assert mealie_list_service.recipe_store[recipe.id] == recipe


def test_mealie_list_service_food_store(mealie_list_service: MealieListService, mealie_foods: list[Food]):
    for food in mealie_foods:
        assert food.name.lower() in mealie_list_service.food_store
        assert mealie_list_service.food_store[food.name.lower()] == food


def test_mealie_list_service_label_store(mealie_list_service: MealieListService, mealie_labels: list[Label]):
    for label in mealie_labels:
        assert label.name.lower() in mealie_list_service.label_store
        assert mealie_list_service.label_store[label.name.lower()] == label


def test_mealie_list_service_get_recipe_url(mealie_list_service: MealieListService, mealie_recipes: list[MealieRecipe]):
    for recipe in mealie_recipes:
        expected_url = f"{mealie_list_service.config.base_url}/recipe/{recipe.slug}"
        recipe_url = mealie_list_service.get_recipe_url(recipe.id)
        assert recipe_url
        assert recipe_url == expected_url

    # return None if the recipe is not found
    assert mealie_list_service.get_recipe_url(random_string()) is None


@pytest.mark.parametrize(
    "service_method,record_list_fixture,",
    [
        ("get_food", "mealie_foods"),
        ("get_label", "mealie_labels"),
    ],
)
def test_mealie_list_service_get_from_text(
    mealie_list_service: MealieListService,
    service_method: str,
    record_list_fixture: str,
    request: pytest.FixtureRequest,
):
    record_list: list = request.getfixturevalue(record_list_fixture)
    record = random.choice(record_list)
    get_func: Callable = getattr(mealie_list_service, service_method)

    fetched_record = get_func(str(record))
    assert fetched_record == record

    # check that no match returns none
    assert get_func(random_string(24601)) is None


def test_mealie_list_service_get_food_fuzzy(mealie_list_service: MealieListService, mealie_foods: list[Food]):
    food = random.choice(mealie_foods)
    food_string = str(food) + random_string(1)

    fetched_food = mealie_list_service.get_food(food_string)
    assert fetched_food == food


def test_mealie_list_service_get_label_from_item(
    mealie_list_service: MealieListService,
    mealie_shopping_lists: list[MealieShoppingListOut],
    mealie_shopping_lists_with_foods_labels_units_recipe: list[MealieShoppingListOut],
):
    shopping_list = random.choice(mealie_shopping_lists_with_foods_labels_units_recipe)
    item = random.choice(shopping_list.list_items)
    assert item.label

    label = mealie_list_service.get_label_from_item(item)
    assert label == item.label

    shopping_list_with_no_labels = random.choice(mealie_shopping_lists)
    item_without_label = random.choice(shopping_list_with_no_labels.list_items)
    assert mealie_list_service.get_label_from_item(item_without_label) is None

    # remove the label from the item, then verify the food label is retrieved
    item.label = None
    assert item.food and item.food.label
    mealie_list_service.update_items([item.cast(MealieShoppingListItemUpdateBulk, recipe_references=[])])

    label = mealie_list_service.get_label_from_item(item)
    assert label
    assert label == item.food.label


@pytest.mark.parametrize(
    "mealie_list_service_fixture,use_foods,overwrite_names",
    [
        ("mealie_list_service", False, False),
        ("mealie_list_service_use_foods", True, False),
        ("mealie_list_service_overwrite_names", True, True),
    ],
)
def test_mealie_list_service_add_food_to_item(
    mealie_list_service_fixture: str,
    use_foods: bool,
    overwrite_names: bool,
    mealie_foods_with_labels: list[Food],
    mealie_labels: list[Label],
    request: pytest.FixtureRequest,
):
    mealie_list_service: MealieListService = request.getfixturevalue(mealie_list_service_fixture)
    item = MealieShoppingListItemCreate(shopping_list_id=random_string(), note=random_string(100), is_food=False)

    food = random.choice(mealie_foods_with_labels)
    assert food.label
    label: Optional[Label] = None
    while label is None or label == food.label:
        label = random.choice(mealie_labels)

    # items with no food and a random note should do nothing
    assert mealie_list_service.add_food_to_item(item) == item

    # items already with a food should do nothing
    item.food_id = food.id
    assert mealie_list_service.add_food_to_item(item) == item

    # items with no food but with a note similar to a food should be matched
    item.food_id = None
    item.note = str(food) + "a"  # food should fuzzy match
    response = mealie_list_service.add_food_to_item(item)
    if not use_foods:
        assert response == item
    elif not overwrite_names:
        assert item.is_food is False
        assert item.food_id is None
        assert item.label_id == food.label.id
    else:
        assert item.is_food is True
        assert item.food_id == food.id
        assert item.label_id == food.label.id
