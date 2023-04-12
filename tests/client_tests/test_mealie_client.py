import random
from collections import defaultdict
from typing import Callable, Type

import pytest

from AppLambda.src.clients.mealie import MealieClient
from AppLambda.src.models.mealie import (
    APIBase,
    AuthToken,
    Food,
    Label,
    MealieEventNotifierOptions,
    MealieEventNotifierOut,
    MealieEventNotifierUpdate,
    MealieRecipe,
    MealieShoppingListItemCreate,
    MealieShoppingListItemOut,
    MealieShoppingListItemUpdateBulk,
    MealieShoppingListOut,
    Unit,
)
from tests.fixtures.databases.mealie.router import MockDBKey, MockMealieServer
from tests.utils import random_bool, random_int, random_string


def test_mealie_client_is_valid(mealie_client: MealieClient):
    assert mealie_client.is_valid

    # reach into the mealie client and make its auth token invalid
    mealie_client.client._client.headers["Authorization"] = f"Bearer {random_string()}"
    assert not mealie_client.is_valid


@pytest.mark.parametrize(
    "client_method, record_list_fixture, record_model,db_key",
    [
        ("get_all_shopping_lists", "mealie_shopping_lists", MealieShoppingListOut, MockDBKey.shopping_lists),
        ("get_all_recipes", "mealie_recipes", MealieRecipe, MockDBKey.recipes),
        ("get_all_foods", "mealie_foods", Food, MockDBKey.foods),
        ("get_all_labels", "mealie_labels", Label, MockDBKey.labels),
    ],
)
def test_mealie_client_get_all_records(
    mealie_server: MockMealieServer,
    mealie_client: MealieClient,
    client_method: str,
    record_list_fixture: str,
    record_model: Type[APIBase],
    db_key: MockDBKey,
    request: pytest.FixtureRequest,
):
    record_list = request.getfixturevalue(record_list_fixture)
    assert record_list  # pre-populate database

    record_store = {id: record_model(**data) for id, data in mealie_server.get_all_records(db_key).items()}
    get_all_func: Callable = getattr(mealie_client, client_method)
    all_records_data = get_all_func()
    all_records = {getattr(record, "id"): record for record in all_records_data}
    assert all_records == record_store


@pytest.mark.parametrize(
    "client_method, record_list_fixture",
    [
        ("get_shopping_list", "mealie_shopping_lists"),
    ],
)
def test_mealie_client_get_one_record(
    mealie_client: MealieClient,
    client_method: str,
    record_list_fixture: str,
    request: pytest.FixtureRequest,
):
    record_list: list = request.getfixturevalue(record_list_fixture)
    record_to_get = random.choice(record_list)
    record_id: str = getattr(record_to_get, "id")

    get_func: Callable = getattr(mealie_client, client_method)
    record = get_func(record_id)
    assert record == record_to_get


@pytest.mark.parametrize(
    "client_method, record_model, db_key, args_callable",
    [
        ("create_auth_token", AuthToken, MockDBKey.user_api_tokens, lambda: (random_string(),)),
        ("create_notifier", MealieEventNotifierOut, MockDBKey.notifiers, lambda: (random_string(), random_string())),
    ],
)
def test_mealie_client_create_record(
    mealie_server: MockMealieServer,
    mealie_client: MealieClient,
    client_method: str,
    record_model: Type[APIBase],
    db_key: MockDBKey,
    args_callable: Callable,
):
    create_func: Callable = getattr(mealie_client, client_method)
    new_record = create_func(*args_callable())

    record_store = {id: record_model(**data) for id, data in mealie_server.get_all_records(db_key).items()}
    assert record_store[getattr(new_record, "id")] == new_record


@pytest.mark.parametrize(
    "client_method, record_model, db_key,record_list_fixture",
    [
        ("delete_auth_token", AuthToken, MockDBKey.user_api_tokens, "mealie_api_tokens"),
        ("delete_notifier", MealieEventNotifierOut, MockDBKey.notifiers, "mealie_notifiers"),
    ],
)
def test_mealie_client_delete_record(
    mealie_server: MockMealieServer,
    mealie_client: MealieClient,
    client_method: str,
    record_model: Type[APIBase],
    db_key: MockDBKey,
    record_list_fixture: str,
    request: pytest.FixtureRequest,
):
    record_list: list = request.getfixturevalue(record_list_fixture)
    record_to_delete = random.choice(record_list)
    record_id: str = getattr(record_to_delete, "id")

    record_store = {id: record_model(**data) for id, data in mealie_server.get_all_records(db_key).items()}
    assert record_store[record_id] == record_to_delete

    delete_func: Callable = getattr(mealie_client, client_method)
    delete_func(record_id)

    record_store = {id: record_model(**data) for id, data in mealie_server.get_all_records(db_key).items()}
    assert record_id not in record_store


def test_mealie_client_update_notifier(
    mealie_server: MockMealieServer, mealie_client: MealieClient, mealie_notifiers: list[MealieEventNotifierOut]
):
    original_record_store = mealie_server.get_all_records(MockDBKey.notifiers)
    notifier = random.choice(mealie_notifiers)
    updated_notifier = mealie_client.update_notifier(
        notifier.cast(MealieEventNotifierUpdate, options=MealieEventNotifierOptions())
    )

    # our database is unchanged when notifiers are updated, so all we need
    # to test is that both the notifier and the database are unchanged
    assert updated_notifier == notifier
    updated_record_store = mealie_server.get_all_records(MockDBKey.notifiers)
    assert updated_record_store == original_record_store


def test_mealie_client_get_all_shopping_list_items(
    mealie_client: MealieClient, mealie_shopping_lists: list[MealieShoppingListOut]
):
    for shopping_list in mealie_shopping_lists:
        list_items = list(mealie_client.get_all_shopping_list_items(shopping_list.id, include_checked=True))
        assert len(list_items) == len(shopping_list.list_items)
        for list_item in list_items:
            assert list_item in shopping_list.list_items

        # make sure we only get unchecked items if specified
        shopping_list_unchecked_list_items = [li for li in shopping_list.list_items if not li.checked]
        unchecked_list_items = list(mealie_client.get_all_shopping_list_items(shopping_list.id, include_checked=False))
        assert len(unchecked_list_items) == len(shopping_list_unchecked_list_items)
        for list_item in unchecked_list_items:
            assert list_item in shopping_list_unchecked_list_items


def test_mealie_client_create_shopping_list_items(
    mealie_server: MockMealieServer,
    mealie_client: MealieClient,
    mealie_shopping_lists: list[MealieShoppingListOut],
    mealie_foods: list[Food],
    mealie_labels: list[Label],
    mealie_units: list[Unit],
):
    original_lists = {
        id: MealieShoppingListOut(**data)
        for id, data in mealie_server.get_all_records(MockDBKey.shopping_lists).items()
    }

    new_items_by_list_id: defaultdict[str, list[MealieShoppingListItemCreate]] = defaultdict(list)
    for i in range(random_int(20, 30)):
        shopping_list = random.choice(mealie_shopping_lists)
        is_food = random_bool()
        food = random.choice(mealie_foods) if random_bool() else None
        label = random.choice(mealie_labels) if random_bool() else None
        unit = random.choice(mealie_units) if random_bool() else None

        new_items_by_list_id[shopping_list.id].append(
            MealieShoppingListItemCreate(
                shopping_list_id=shopping_list.id,
                checked=False,
                position=i,
                note=random_string(),
                quantity=random_int(0, 100),
                is_food=is_food,
                food_id=food.id if food and is_food else None,
                label_id=label.id if label else None,
                unit_id=unit.id if unit and is_food else None,
            )
        )

    created_items_by_list_id: defaultdict[str, list[MealieShoppingListItemOut]] = defaultdict(list)
    for shopping_list_id, new_items in new_items_by_list_id.items():
        response = mealie_client.create_shopping_list_items(new_items)
        assert not response.updated_items
        assert not response.deleted_items

        created_items_by_list_id[shopping_list_id].extend(response.created_items)

    updated_lists = {
        id: MealieShoppingListOut(**data)
        for id, data in mealie_server.get_all_records(MockDBKey.shopping_lists).items()
    }

    # compare updated list against original list
    for list_id in created_items_by_list_id:
        original_list_items = original_lists[list_id].list_items
        updated_list_items = updated_lists[list_id].list_items
        created_items = created_items_by_list_id[list_id]

        assert created_items
        assert len(updated_list_items) == len(original_list_items) + len(created_items)
        for item in created_items:
            assert item not in original_list_items
            assert item in updated_list_items


def test_mealie_client_update_shopping_list_items(
    mealie_server: MockMealieServer,
    mealie_client: MealieClient,
    mealie_shopping_lists: list[MealieShoppingListOut],
):
    original_shopping_list = random.choice(mealie_shopping_lists)
    original_items = random.sample(
        original_shopping_list.list_items, random_int(2, len(original_shopping_list.list_items))
    )

    original_shopping_list_items_by_id = {item.id: item for item in original_shopping_list.list_items}

    items_to_update: list[MealieShoppingListItemUpdateBulk] = [
        item.cast(MealieShoppingListItemUpdateBulk, note=random_string()) for item in original_items
    ]
    response = mealie_client.update_shopping_list_items(items_to_update)
    assert not response.created_items
    assert response.updated_items
    assert not response.deleted_items
    updated_items_by_id = {item.id: item for item in response.updated_items}

    updated_shopping_list_data = mealie_server.get_record_by_id(MockDBKey.shopping_lists, original_shopping_list.id)
    assert updated_shopping_list_data
    updated_shopping_list = MealieShoppingListOut(**updated_shopping_list_data)

    # compare updated list against client response and original list
    assert len(updated_shopping_list.list_items) == len(original_shopping_list.list_items)
    for item in updated_shopping_list.list_items:
        if item.id in updated_items_by_id:
            assert item == updated_items_by_id[item.id] != original_shopping_list_items_by_id[item.id]
        else:
            assert item == original_shopping_list_items_by_id[item.id]


def test_mealie_client_delete_shopping_list_items(
    mealie_server: MockMealieServer,
    mealie_client: MealieClient,
    mealie_shopping_lists: list[MealieShoppingListOut],
):
    original_shopping_list = random.choice(mealie_shopping_lists)
    items_to_delete = random.sample(original_shopping_list.list_items, 2)
    mealie_client.delete_shopping_list_items([item.id for item in items_to_delete])

    updated_list_data = mealie_server.get_record_by_id(MockDBKey.shopping_lists, original_shopping_list.id)
    assert updated_list_data
    updated_list = MealieShoppingListOut(**updated_list_data)

    assert len(updated_list.list_items) == len(original_shopping_list.list_items) - len(items_to_delete)
    for item in items_to_delete:
        assert item in original_shopping_list.list_items
        assert item not in updated_list.list_items
