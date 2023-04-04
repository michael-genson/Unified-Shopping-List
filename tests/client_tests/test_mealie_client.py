import random
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
    MealieShoppingListOut,
)
from tests.fixtures.databases.mealie.router import MockDBKey, MockMealieServer
from tests.utils import random_string


def test_mealie_client_is_valid(mealie_client: MealieClient):
    assert mealie_client.is_valid

    # reach into the mealie client and make its auth token invalid
    mealie_client.client._client.headers["Authorization"] = f"Bearer {random_string()}"
    assert not mealie_client.is_valid


@pytest.mark.parametrize(
    "client_function,record_model,db_key",
    [
        ("get_all_shopping_lists", MealieShoppingListOut, MockDBKey.shopping_lists),
        ("get_all_recipes", MealieRecipe, MockDBKey.recipes),
        ("get_all_foods", Food, MockDBKey.foods),
        ("get_all_labels", Label, MockDBKey.labels),
    ],
)
def test_mealie_client_get_all_records(
    mealie_server: MockMealieServer,
    mealie_client: MealieClient,
    client_function: str,
    record_model: Type[APIBase],
    db_key: MockDBKey,
):
    record_store = {id: record_model(**data) for id, data in mealie_server.get_all_records(db_key).items()}
    get_all_func: Callable = getattr(mealie_client, client_function)
    all_records_data = get_all_func()
    all_records = {getattr(record, "id"): record for record in all_records_data}
    assert all_records == record_store


@pytest.mark.parametrize(
    "client_function,record_list_fixture",
    [
        ("get_shopping_list", "mealie_shopping_lists"),
    ],
)
def test_mealie_client_get_one_record(
    mealie_client: MealieClient,
    client_function: str,
    record_list_fixture: str,
    request: pytest.FixtureRequest,
):
    record_list: list = request.getfixturevalue(record_list_fixture)
    record_to_get = random.choice(record_list)
    record_id: str = getattr(record_to_get, "id")

    get_func: Callable = getattr(mealie_client, client_function)
    record = get_func(record_id)
    assert record == record_to_get


@pytest.mark.parametrize(
    "client_function,record_model,db_key,args_callable",
    [
        ("create_auth_token", AuthToken, MockDBKey.user_api_tokens, lambda: (random_string(),)),
        ("create_notifier", MealieEventNotifierOut, MockDBKey.notifiers, lambda: (random_string(), random_string())),
    ],
)
def test_mealie_client_create_record(
    mealie_server: MockMealieServer,
    mealie_client: MealieClient,
    client_function: str,
    record_model: Type[APIBase],
    db_key: MockDBKey,
    args_callable: Callable,
):
    create_func: Callable = getattr(mealie_client, client_function)
    new_record = create_func(*args_callable())

    record_store = {id: record_model(**data) for id, data in mealie_server.get_all_records(db_key).items()}
    assert record_store[getattr(new_record, "id")] == new_record


@pytest.mark.parametrize(
    "client_function,record_model,db_key,record_list_fixture",
    [
        ("delete_auth_token", AuthToken, MockDBKey.user_api_tokens, "mealie_api_tokens"),
        ("delete_notifier", MealieEventNotifierOut, MockDBKey.notifiers, "mealie_notifiers"),
    ],
)
def test_mealie_client_delete_record(
    mealie_server: MockMealieServer,
    mealie_client: MealieClient,
    client_function: str,
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

    delete_func: Callable = getattr(mealie_client, client_function)
    delete_func(record_id)

    record_store = {id: record_model(**data) for id, data in mealie_server.get_all_records(db_key).items()}
    assert record_id not in record_store


def test_mealie_client_update_notifier(
    mealie_server: MockMealieServer, mealie_client: MealieClient, mealie_notifiers: list[MealieEventNotifierOut]
):
    existing_record_store = mealie_server.get_all_records(MockDBKey.notifiers)
    notifier = random.choice(mealie_notifiers)
    updated_notifier = mealie_client.update_notifier(
        notifier.cast(MealieEventNotifierUpdate, options=MealieEventNotifierOptions())
    )

    # our database is unchanged when notifiers are updated, so all we need
    # to test is that both the notifier and the database are unchanged
    assert updated_notifier == notifier
    updated_record_store = mealie_server.get_all_records(MockDBKey.notifiers)
    assert updated_record_store == existing_record_store


def test_mealie_client_get_all_shopping_list_items(
    mealie_client: MealieClient,
    mealie_shopping_lists: list[MealieShoppingListOut],
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
