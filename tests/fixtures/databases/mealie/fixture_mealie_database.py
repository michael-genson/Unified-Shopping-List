import random
from datetime import datetime
from uuid import uuid4

import pytest
from pytest import MonkeyPatch

from AppLambda.src.clients.mealie import MealieBaseClient
from AppLambda.src.models.mealie import (
    AuthToken,
    Food,
    Label,
    MealieEventNotifierOut,
    MealieRecipe,
    MealieShoppingListItemOut,
    MealieShoppingListItemRecipeRefOut,
    MealieShoppingListOut,
    MealieShoppingListRecipeRef,
    Unit,
)
from tests.utils import random_bool, random_int, random_string

from .router import MockDBKey, MockMealieServer

mock_server = MockMealieServer()


@pytest.fixture()
def mealie_server() -> MockMealieServer:
    return mock_server


@pytest.fixture()
def mealie_foods() -> list[Food]:
    foods = [Food(id=str(uuid4()), name=random_string(), description=random_string()) for _ in range(10)]
    for food in foods:
        assert food.id
        mock_server._insert_one(MockDBKey.foods, food.id, food.dict())

    return foods


@pytest.fixture()
def mealie_foods_with_labels(mealie_labels: list[Label]) -> list[Food]:
    foods = [
        Food(id=str(uuid4()), name=random_string(), description=random_string(), label=random.choice(mealie_labels))
        for _ in range(10)
    ]
    for food in foods:
        assert food.id
        mock_server._insert_one(MockDBKey.foods, food.id, food.dict())

    return foods


@pytest.fixture()
def mealie_labels() -> list[Label]:
    labels = [Label(id=str(uuid4()), name=random_string(), color="#FFFFFF") for _ in range(10)]
    for label in labels:
        mock_server._insert_one(MockDBKey.labels, label.id, label.dict())

    return labels


@pytest.fixture()
def mealie_notifiers() -> list[MealieEventNotifierOut]:
    notifiers = [
        MealieEventNotifierOut(id=str(uuid4()), group_id=mock_server.group_id, name=random_string()) for _ in range(10)
    ]
    for notifier in notifiers:
        mock_server._insert_one(MockDBKey.notifiers, notifier.id, notifier.dict())

    return notifiers


@pytest.fixture()
def mealie_recipes() -> list[MealieRecipe]:
    recipes = [MealieRecipe(id=str(uuid4()), slug=random_string(), name=random_string()) for _ in range(10)]
    for recipe in recipes:
        mock_server._insert_one(MockDBKey.recipes, recipe.id, recipe.dict())

    return recipes


@pytest.fixture()
def mealie_shopping_lists() -> list[MealieShoppingListOut]:
    shopping_lists: list[MealieShoppingListOut] = []
    for _ in range(10):
        list_id = str(uuid4())
        items = [
            MealieShoppingListItemOut(
                id=str(uuid4()),
                shopping_list_id=list_id,
                checked=random_bool(),
                position=i,
                is_food=False,
                note=random_string(),
                quantity=random_int(0, 10),
                display=random_string(),
            )
            for i in range(random_int(10, 20))
        ]
        shopping_lists.append(
            MealieShoppingListOut(
                id=list_id,
                name=random_string(),
                list_items=items,
                created_at=datetime.now(),
                update_at=datetime.now(),
            )
        )

    for shopping_list in shopping_lists:
        mock_server._insert_one(MockDBKey.shopping_lists, shopping_list.id, shopping_list.dict())

    return shopping_lists


@pytest.fixture()
def mealie_shopping_lists_with_foods_labels_units_recipe(
    mealie_foods_with_labels: list[Food], mealie_recipes: list[MealieRecipe], mealie_units: list[Unit]
) -> list[MealieShoppingListOut]:
    shopping_lists: list[MealieShoppingListOut] = []
    for _ in range(10):
        list_id = str(uuid4())
        food = random.choice(mealie_foods_with_labels)
        assert food.label
        unit = random.choice(mealie_units)

        number_of_items = random_int(10, 20)
        recipe = random.choice(mealie_recipes)
        recipe_references = [
            MealieShoppingListRecipeRef(
                id=str(uuid4()),
                recipe_id=recipe.id,
                shopping_list_id=list_id,
                recipe_quantity=number_of_items,
                recipe=recipe,
            )
        ]

        items: list[MealieShoppingListItemOut] = []
        for i in range(number_of_items):
            item_id = str(uuid4())
            items.append(
                MealieShoppingListItemOut(
                    id=item_id,
                    shopping_list_id=list_id,
                    checked=random_bool(),
                    position=i,
                    is_food=True,
                    note=random_string(),
                    quantity=random.uniform(0, 10),
                    display=random_string(),
                    food_id=food.id,
                    food=food,
                    label_id=food.label.id,
                    label=food.label,
                    unit_id=unit.id,
                    unit=unit,
                    recipe_references=[
                        MealieShoppingListItemRecipeRefOut(
                            id=str(uuid4()),
                            recipe_id=recipe.id,
                            recipe_quantity=1,
                            recipe_scale=1,
                            shopping_list_item_id=item_id,
                        )
                    ],
                )
            )

        shopping_lists.append(
            MealieShoppingListOut(
                id=list_id,
                name=random_string(),
                list_items=items,
                recipe_references=recipe_references,
                created_at=datetime.now(),
                update_at=datetime.now(),
            )
        )

    for shopping_list in shopping_lists:
        mock_server._insert_one(MockDBKey.shopping_lists, shopping_list.id, shopping_list.dict())

    return shopping_lists


@pytest.fixture()
def mealie_units() -> list[Unit]:
    units = [
        Unit(
            id=str(uuid4()),
            name=random_string(),
            description=random_string(),
            fraction=random_bool(),
            abbreviation=random_string(3),
            use_abbreviation=random_bool(),
        )
        for _ in range(10)
    ]

    for unit in units:
        assert unit.id
        mock_server._insert_one(MockDBKey.units, unit.id, unit.dict())

    return units


@pytest.fixture()
def mealie_api_tokens() -> list[AuthToken]:
    tokens = [AuthToken(id=str(uuid4()), token=str(uuid4()), name=random_string()) for _ in range(10)]
    for token in tokens:
        mock_server._insert_one(MockDBKey.user_api_tokens, token.id, token.dict())

    return tokens


@pytest.fixture(scope="session", autouse=True)
def mock_mealie_server():
    """Replace all Mealie API calls with locally mocked database calls"""

    mp = MonkeyPatch()
    mp.setattr(MealieBaseClient, "_get_client", lambda *args, **kwargs: mock_server)
    yield


@pytest.fixture(autouse=True)
def clean_up_database():
    yield
    mock_server.db.clear()
