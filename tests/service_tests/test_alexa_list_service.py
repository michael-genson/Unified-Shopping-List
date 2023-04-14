import random
from typing import Optional

import pytest

from AppLambda.src.models.account_linking import NotLinkedError
from AppLambda.src.models.alexa import AlexaListItemCreateIn, AlexaListItemOut, AlexaListItemUpdateBulkIn, AlexaListOut
from AppLambda.src.models.core import User
from AppLambda.src.services.alexa import AlexaListService
from tests.utils.generators import random_int, random_string

# TODO: verify service list cache is properly maintained for all operations
# TODO: verify service list cache is returned as a deep copy, rather than as a reference


def test_alexa_list_service_unlinked_user(user_linked_mealie: User):
    with pytest.raises(NotLinkedError):
        AlexaListService(user_linked_mealie)


def test_alexa_list_service_get_all_lists(
    alexa_list_service: AlexaListService, alexa_lists_with_items: list[AlexaListOut]
):
    all_lists = alexa_list_service.get_all_lists()

    # lists fetched via get_all_lists only contain a summary of list data,
    # so we just make sure all list ids are present, rather than the full list instance
    all_list_ids = set(alexa_list.list_id for alexa_list in all_lists.lists)
    for alexa_list in alexa_lists_with_items:
        assert alexa_list.list_id in all_list_ids


def test_alexa_list_service_get_list(alexa_list_service: AlexaListService, alexa_lists_with_items: list[AlexaListOut]):
    alexa_list = random.choice(alexa_lists_with_items)
    fetched_list = alexa_list_service.get_list(alexa_list.list_id)
    assert fetched_list == alexa_list


def test_alexa_list_service_get_list_cache(
    alexa_list_service: AlexaListService, alexa_lists_with_items: list[AlexaListOut]
):
    alexa_list = random.choice(alexa_lists_with_items)

    fetched_list = alexa_list_service.get_list(alexa_list.list_id)
    assert fetched_list.items
    cached_list = alexa_list_service.lists[alexa_list.list_id]
    assert cached_list.items

    # verify lists are returned as deep copies, rather than as a reference
    assert fetched_list is not cached_list
    for fetched_item, cached_item in zip(fetched_list.items, cached_list.items):
        assert fetched_item is not cached_item


def test_alexa_list_service_get_invalid_list(alexa_list_service: AlexaListService):
    with pytest.raises(Exception):  # TODO: update this to a custom exception type
        alexa_list_service.get_list(random_string())


def test_alexa_list_service_get_list_item(
    alexa_list_service: AlexaListService, alexa_lists_with_items: list[AlexaListOut]
):
    alexa_list = random.choice(alexa_lists_with_items)
    assert alexa_list.items
    alexa_list_item = random.choice(alexa_list.items)

    fetched_item = alexa_list_service.get_list_item(alexa_list.list_id, alexa_list_item.id)
    assert fetched_item
    assert fetched_item == alexa_list_item


def test_alexa_list_service_get_list_item_cache(
    alexa_list_service: AlexaListService, alexa_lists_with_items: list[AlexaListOut]
):
    alexa_list = random.choice(alexa_lists_with_items)
    assert alexa_list.items
    alexa_item = random.choice(alexa_list.items)

    fetched_item = alexa_list_service.get_list_item(alexa_list.list_id, alexa_item.id)
    cached_list = alexa_list_service.lists[alexa_list.list_id]
    assert cached_list.items
    cached_item: Optional[AlexaListItemOut] = None
    for _cached_item in cached_list.items:
        if _cached_item.id == alexa_item.id:
            cached_item = _cached_item
            break

    assert cached_item
    assert cached_item is not fetched_item


def test_alexa_list_service_get_invalid_list_item(
    alexa_list_service: AlexaListService, alexa_lists_with_items: list[AlexaListOut]
):
    # an invalid list throws an error
    with pytest.raises(Exception):  # TODO: update this to a custom exception type
        alexa_list_service.get_list_item(random_string(), random_string())

    # a valid list with an invalid item id returns None
    alexa_list = random.choice(alexa_lists_with_items)
    fetched_item = alexa_list_service.get_list_item(alexa_list.list_id, random_string())
    assert fetched_item is None


def test_alexa_list_service_create_list_items(
    alexa_list_service: AlexaListService, alexa_lists_with_items: list[AlexaListOut]
):
    alexa_list = random.choice(alexa_lists_with_items)
    items_to_create = [AlexaListItemCreateIn(value=random_string()) for _ in range(random_int(10, 20))]
    response = alexa_list_service.create_list_items(alexa_list.list_id, items_to_create)

    new_items = response.list_items
    assert len(new_items) == len(items_to_create)

    # check that all values are present and order is preserved
    for item_to_create, new_item in zip(items_to_create, new_items):
        assert item_to_create.value == new_item.value

    fetched_list = alexa_list_service.get_list(alexa_list.list_id)
    assert fetched_list.items
    for new_item in new_items:
        assert new_item in fetched_list.items


def test_alexa_list_service_create_list_items_cache(
    alexa_list_service: AlexaListService, alexa_lists_with_items: list[AlexaListOut]
):
    alexa_list = random.choice(alexa_lists_with_items)
    items_to_create = [AlexaListItemCreateIn(value=random_string()) for _ in range(random_int(10, 20))]
    response = alexa_list_service.create_list_items(alexa_list.list_id, items_to_create)

    new_items = response.list_items
    cached_list = alexa_list_service.lists[alexa_list.list_id]
    assert cached_list.items
    for new_item in new_items:
        cached_item: Optional[AlexaListItemOut] = None
        for _cached_item in cached_list.items:
            if _cached_item.id == new_item.id:
                cached_item = _cached_item
                break

        assert cached_item
        assert cached_item is not new_item


def test_alexa_list_service_update_list_items(
    alexa_list_service: AlexaListService, alexa_lists_with_items: list[AlexaListOut]
):
    original_list = random.choice(alexa_lists_with_items)
    assert original_list.items
    original_items = random.sample(original_list.items, 5)

    items_to_update = [
        AlexaListItemUpdateBulkIn(id=original_item.id, value=random_string()) for original_item in original_items
    ]
    response = alexa_list_service.update_list_items(original_list.list_id, items_to_update)

    original_items_by_id = {original_item.id: original_item for original_item in original_items}
    items_to_update_by_id = {item_to_update.id: item_to_update for item_to_update in items_to_update}
    updated_items_by_id = {updated_item.id: updated_item for updated_item in response.list_items}
    assert len(original_items_by_id) == len(items_to_update_by_id) == len(updated_items_by_id)
    assert set(original_items_by_id.keys()) == set(items_to_update_by_id.keys()) == set(updated_items_by_id.keys())

    # verify the items were properly updated
    for item_id in items_to_update_by_id:
        original_item = original_items_by_id[item_id]
        item_to_update = items_to_update_by_id[item_id]
        updated_item = updated_items_by_id[item_id]

        assert original_item.value != item_to_update.value
        assert item_to_update.value == updated_item.value
        assert original_item.version == updated_item.version - 1

    # verify the list has both the changed and unchanged items
    fetched_list = alexa_list_service.get_list(original_list.list_id)
    assert fetched_list.items
    for fetched_item in fetched_list.items:
        if fetched_item.id in updated_items_by_id:
            assert fetched_item == updated_items_by_id[fetched_item.id]
        else:
            assert fetched_item in original_list.items


def test_alexa_list_service_update_list_items_cache(
    alexa_list_service: AlexaListService, alexa_lists_with_items: list[AlexaListOut]
):
    alexa_list = random.choice(alexa_lists_with_items)
    assert alexa_list.items
    items_to_update = [
        AlexaListItemUpdateBulkIn(id=original_item.id, value=random_string())
        for original_item in random.sample(alexa_list.items, 5)
    ]
    response = alexa_list_service.update_list_items(alexa_list.list_id, items_to_update)

    updated_items = response.list_items
    cached_list = alexa_list_service.lists[alexa_list.list_id]
    assert cached_list.items
    for updated_item in updated_items:
        cached_item: Optional[AlexaListItemOut] = None
        for _cached_item in cached_list.items:
            if _cached_item.id == updated_item.id:
                cached_item = _cached_item
                break

        assert cached_item
        assert cached_item is not updated_item
