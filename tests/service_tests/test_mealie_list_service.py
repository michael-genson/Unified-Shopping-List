import random
from typing import Callable, Type

import pytest

from AppLambda.src.models.account_linking import NotLinkedError
from AppLambda.src.models.core import User
from AppLambda.src.models.mealie import (
    APIBase,
    Food,
    Label,
    MealieRecipe,
    MealieShoppingListItemCreate,
    MealieShoppingListItemExtras,
    MealieShoppingListItemOut,
    MealieShoppingListItemUpdateBulk,
    MealieShoppingListOut,
)
from AppLambda.src.services.mealie import MealieListService
from tests.fixtures.databases.mealie.mock_mealie_database import MockMealieDBKey, MockMealieServer
from tests.utils.generators import random_int, random_string

# TODO: verify service list cache is properly maintained for all operations


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
    "service_method, record_list_fixture",
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
    "mealie_list_service_fixture, use_foods, overwrite_names",
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
    label: Label | None = None
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


@pytest.mark.parametrize(
    "service_method, record_list_fixture, record_model, db_key",
    [
        ("get_all_lists", "mealie_shopping_lists", MealieShoppingListOut, MockMealieDBKey.shopping_lists),
    ],
)
def test_mealie_list_service_get_all(
    mealie_server: MockMealieServer,
    mealie_list_service: MealieListService,
    service_method: str,
    record_list_fixture: str,
    record_model: Type[APIBase],
    db_key: MockMealieDBKey,
    request: pytest.FixtureRequest,
):
    record_list = request.getfixturevalue(record_list_fixture)
    assert record_list  # pre-populate database

    record_store = {id: record_model(**data) for id, data in mealie_server.get_all_records(db_key).items()}
    get_all_func: Callable = getattr(mealie_list_service, service_method)
    all_records_data = get_all_func()
    all_records = {getattr(record, "id"): record for record in all_records_data}
    assert all_records == record_store


def test_mealie_list_service_get_all_list_items(
    mealie_list_service: MealieListService, mealie_shopping_lists: list[MealieShoppingListOut]
):
    shopping_list = random.choice(mealie_shopping_lists)

    # unchecked is done first to avoid caching checked items
    expected_checked_items = [item for item in shopping_list.list_items if not item.checked]
    all_unchecked_items = mealie_list_service.get_all_list_items(shopping_list.id, include_all_checked=False)
    assert len(all_unchecked_items) == len(expected_checked_items)
    for item in all_unchecked_items:
        assert item in expected_checked_items

    expected_items = shopping_list.list_items
    all_items = mealie_list_service.get_all_list_items(shopping_list.id, include_all_checked=True)
    assert len(all_items) == len(expected_items)
    for item in all_items:
        assert item in expected_items


def test_mealie_list_service_get_all_list_items_cache(
    mealie_list_service: MealieListService, mealie_shopping_lists: list[MealieShoppingListOut]
):
    mealie_list = random.choice(mealie_shopping_lists)
    assert mealie_list.list_items

    # verify items are returned as deep copies, rather than as a reference
    fetched_items = mealie_list_service.get_all_list_items(mealie_list.id)
    cached_items = mealie_list_service._list_items_cache[mealie_list.id]
    assert fetched_items is not cached_items
    for fetched_item, cached_item in zip(fetched_items, cached_items):
        assert fetched_item is not cached_item


def test_mealie_list_service_get_item(
    mealie_list_service: MealieListService, mealie_shopping_lists: list[MealieShoppingListOut]
):
    # get a list item that isn't checked
    list_item: MealieShoppingListItemOut | None = None
    for shopping_list in mealie_shopping_lists:
        for li in shopping_list.list_items:
            if not li.checked:
                list_item = li
                break

        if list_item:
            break

    assert list_item
    assert mealie_list_service.get_item(list_item.shopping_list_id, list_item.id) == list_item

    # verify a random id returns None
    assert mealie_list_service.get_item(list_item.shopping_list_id, random_string()) is None


def test_mealie_list_service_get_item_cache(
    mealie_list_service: MealieListService, mealie_shopping_lists: list[MealieShoppingListOut]
):
    mealie_list = random.choice(mealie_shopping_lists)
    assert mealie_list.list_items
    mealie_item = random.choice(mealie_list.list_items)

    # verify items are returned as deep copies, rather than as a reference
    fetched_item = mealie_list_service.get_item(mealie_list.id, mealie_item.id)
    assert fetched_item

    cached_items = mealie_list_service._list_items_cache[mealie_list.id]
    cached_item: MealieShoppingListItemOut | None = None
    for _item in cached_items:
        if _item.id == mealie_item.id:
            cached_item = _item
            break

    assert cached_item
    assert cached_item is not fetched_item


def test_mealie_list_service_get_item_by_extra(
    mealie_list_service: MealieListService, mealie_shopping_lists: list[MealieShoppingListOut]
):
    list_item = random.choice(random.choice(mealie_shopping_lists).list_items)

    # give the item an extra
    alexa_item_id = random_string()
    list_item_to_update = list_item.cast(MealieShoppingListItemUpdateBulk)
    list_item_to_update.checked = False
    list_item_to_update.extras = MealieShoppingListItemExtras(alexa_item_id=alexa_item_id)
    mealie_list_service.update_items([list_item_to_update])

    updated_list_item = mealie_list_service.get_item(list_item.shopping_list_id, list_item.id)
    assert updated_list_item
    assert (
        mealie_list_service.get_item_by_extra(list_item.shopping_list_id, "alexa_item_id", alexa_item_id)
        == updated_list_item
    )

    # verify a random value returns None
    assert mealie_list_service.get_item_by_extra(list_item.shopping_list_id, "alexa_item_id", random_string()) is None


def test_mealie_list_service_get_item_by_extra_cache(
    mealie_list_service: MealieListService, mealie_shopping_lists: list[MealieShoppingListOut]
):
    list_item = random.choice(random.choice(mealie_shopping_lists).list_items)

    # give the item an extra
    alexa_item_id = random_string()
    list_item_to_update = list_item.cast(MealieShoppingListItemUpdateBulk)
    list_item_to_update.checked = False
    list_item_to_update.extras = MealieShoppingListItemExtras(alexa_item_id=alexa_item_id)
    mealie_list_service.update_items([list_item_to_update])

    updated_list_item = mealie_list_service.get_item(list_item.shopping_list_id, list_item.id)
    assert updated_list_item

    # verify items are returned as deep copies, rather than as a reference
    fetched_item = mealie_list_service.get_item_by_extra(list_item.shopping_list_id, "alexa_item_id", alexa_item_id)
    assert fetched_item

    cached_items = mealie_list_service._list_items_cache[updated_list_item.shopping_list_id]
    cached_item: MealieShoppingListItemOut | None = None
    for _item in cached_items:
        if _item.id == list_item.id:
            cached_item = _item
            break

    assert cached_item
    assert cached_item is not fetched_item


def test_mealie_list_service_create_items(
    mealie_list_service: MealieListService, mealie_shopping_lists: list[MealieShoppingListOut]
):
    shopping_list = random.choice(mealie_shopping_lists)
    original_items = shopping_list.list_items
    items_to_create = [
        MealieShoppingListItemCreate(
            shopping_list_id=shopping_list.id,
            checked=False,
            position=i,
            note=random_string(),
            quantity=random.uniform(1, 10),
        )
        for i in range(random_int(3, 10))
    ]
    new_item_notes = set(item.note for item in items_to_create if item.note)
    assert new_item_notes

    mealie_list_service.create_items(items_to_create)
    updated_list_items = mealie_list_service.get_all_list_items(shopping_list.id, include_all_checked=True)

    # verify all new items are present
    assert len(updated_list_items) == len(original_items) + len(items_to_create)
    for item in updated_list_items:
        if item in original_items:
            continue

        assert item.note
        new_item_notes.remove(item.note)

    assert not new_item_notes


def test_mealie_list_service_update_items(
    mealie_list_service: MealieListService, mealie_shopping_lists: list[MealieShoppingListOut]
):
    shopping_list = random.choice(mealie_shopping_lists)
    original_items = shopping_list.list_items
    update_items = [
        item.cast(MealieShoppingListItemUpdateBulk, note=random_string())
        for item in random.sample(original_items, random_int(3, len(original_items)))
    ]

    mealie_list_service.update_items(update_items)
    original_items_map = {item.id: item for item in original_items}
    updated_items_map = {item.id: item for item in update_items}

    updated_items = mealie_list_service.get_all_list_items(shopping_list.id, include_all_checked=True)
    assert len(updated_items) == len(original_items)
    for item in updated_items:
        if item.id not in updated_items_map:
            assert item.note == original_items_map[item.id].note
        else:
            assert item.note == updated_items_map[item.id].note != original_items_map[item.id].note


def test_mealie_list_service_delete_items(
    mealie_list_service: MealieListService, mealie_shopping_lists: list[MealieShoppingListOut]
):
    shopping_list = random.choice(mealie_shopping_lists)
    original_items = shopping_list.list_items
    items_to_delete = random.sample(original_items, random_int(3, len(original_items)))

    mealie_list_service.delete_items(items_to_delete)
    deleted_item_ids = set(item.id for item in items_to_delete)

    updated_items = mealie_list_service.get_all_list_items(shopping_list.id, include_all_checked=True)
    assert len(updated_items) == len(original_items) - len(items_to_delete)
    for item in original_items:
        assert bool(item.id in deleted_item_ids) ^ bool(item.id not in deleted_item_ids)


def test_mealie_list_service_bulk_handle_items(
    mealie_list_service: MealieListService, mealie_shopping_lists: list[MealieShoppingListOut]
):
    shopping_list = random.choice(mealie_shopping_lists)
    original_items = shopping_list.list_items
    items_to_create = [
        MealieShoppingListItemCreate(
            shopping_list_id=shopping_list.id,
            checked=False,
            position=i,
            note=random_string(100),
            quantity=random.uniform(1, 10),
        )
        for i in range(random_int(3, 10))
    ]
    items_to_delete = random.sample(original_items, random_int(1, 3))
    items_to_update = [
        item.cast(MealieShoppingListItemUpdateBulk, note=random_string(100))
        for item in random.sample([item for item in original_items if item not in items_to_delete], random_int(1, 3))
    ]

    assert items_to_create and items_to_update and items_to_delete

    original_item_map = {item.id: item for item in original_items}
    new_item_notes = set(item.note for item in items_to_create if item.note)
    updated_item_note_map = {item.id: item.note for item in items_to_update if item.note}
    deleted_item_ids = set(item.id for item in items_to_delete)

    mealie_list_service.bulk_handle_items(
        create_items=items_to_create, update_items=items_to_update, delete_items=items_to_delete
    )

    modified_items = mealie_list_service.get_all_list_items(shopping_list.id, include_all_checked=True)
    assert len(modified_items) == len(original_items) + len(items_to_create) - len(items_to_delete)
    for item in modified_items:
        assert item.id not in deleted_item_ids
        if item.id in updated_item_note_map:
            assert item.note == updated_item_note_map[item.id] != original_item_map[item.id].note
        elif item.note in new_item_notes:
            assert item.id not in original_item_map
        else:
            assert item.id in original_item_map
            assert item == original_item_map[item.id]


def test_mealie_list_service_item_positions(
    mealie_list_service: MealieListService, mealie_shopping_lists: list[MealieShoppingListOut]
):
    shopping_list = random.choice(mealie_shopping_lists)
    known_notes = [random_string(100) for _ in range((random_int(3, 10)))]
    items_to_create = [
        MealieShoppingListItemCreate(
            shopping_list_id=shopping_list.id,
            checked=False,
            note=note,
            quantity=random.uniform(1, 10),
        )
        for note in known_notes
    ]

    mealie_list_service.create_items(items_to_create)
    fetched_list_items = mealie_list_service.get_all_list_items(shopping_list.id)

    # verify all items have unique positions
    seen_item_positions = set[int]()
    for item in fetched_list_items:
        assert item.position not in seen_item_positions
        seen_item_positions.add(item.position)

    # verify the new items are at the end of the list when sorted by position
    fetched_list_items.sort(key=lambda x: x.position)
    new_items = fetched_list_items[len(fetched_list_items) - len(known_notes) :]
    for new_item, note in zip(new_items, known_notes, strict=True):
        assert new_item.note == note
