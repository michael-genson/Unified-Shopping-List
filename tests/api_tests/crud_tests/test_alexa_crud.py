import random

import pytest
from fastapi.testclient import TestClient

from AppLambda.src.models.alexa import (
    AlexaListCollectionOut,
    AlexaListItemCollectionOut,
    AlexaListItemCreateIn,
    AlexaListItemOut,
    AlexaListItemUpdateBulkIn,
    AlexaListItemUpdateIn,
    AlexaListOut,
)
from AppLambda.src.models.core import User
from AppLambda.src.routes import alexa
from AppLambda.src.services.alexa import AlexaListService
from tests.utils.generators import random_int, random_string
from tests.utils.users import get_auth_headers


def test_alexa_crud_get_all_lists(
    api_client: TestClient, user_linked: User, alexa_lists_with_items: list[AlexaListOut]
):
    response = api_client.get(alexa.api_router.url_path_for("get_all_lists"), headers=get_auth_headers(user_linked))
    response.raise_for_status()

    # lists fetched via get_all_lists only contain a summary of list data,
    # so we just make sure all list ids are present, rather than the full list instance
    list_response = AlexaListCollectionOut.parse_obj(response.json())
    all_list_ids = set(alexa_list.list_id for alexa_list in list_response.lists)
    for alexa_list in alexa_lists_with_items:
        assert alexa_list.list_id in all_list_ids


def test_alexa_crud_get_all_lists_unlinked(api_client: TestClient, user_linked_mealie: User):
    response = api_client.get(
        alexa.api_router.url_path_for("get_all_lists"), headers=get_auth_headers(user_linked_mealie)
    )
    assert response.status_code == 401


def test_alexa_crud_get_list(api_client: TestClient, user_linked: User, alexa_lists_with_items: list[AlexaListOut]):
    alexa_list = random.choice(alexa_lists_with_items)
    response = api_client.get(
        alexa.api_router.url_path_for("get_list", list_id=alexa_list.list_id),
        headers=get_auth_headers(user_linked),
    )
    response.raise_for_status()

    fetched_list = AlexaListOut.parse_obj(response.json())
    assert fetched_list == alexa_list


@pytest.mark.skip  # TODO: un-skip when incorrect list handling is done
def test_alexa_crud_get_invalid_list(api_client: TestClient, user_linked: User):
    response = api_client.get(
        alexa.api_router.url_path_for("get_list", list_id=random_string()),
        headers=get_auth_headers(user_linked),
    )
    assert response.status_code == 404


def test_alexa_crud_get_list_unlinked(
    api_client: TestClient, user_linked_mealie: User, alexa_lists_with_items: list[AlexaListOut]
):
    alexa_list = random.choice(alexa_lists_with_items)
    response = api_client.get(
        alexa.api_router.url_path_for("get_list", list_id=alexa_list.list_id),
        headers=get_auth_headers(user_linked_mealie),
    )
    assert response.status_code == 401


def test_alexa_crud_get_list_item(
    api_client: TestClient, user_linked: User, alexa_lists_with_items: list[AlexaListOut]
):
    alexa_list = random.choice(alexa_lists_with_items)
    assert alexa_list.items
    alexa_list_item = random.choice(alexa_list.items)

    response = api_client.get(
        alexa.api_router.url_path_for("get_list_item", list_id=alexa_list.list_id, item_id=alexa_list_item.id),
        headers=get_auth_headers(user_linked),
    )
    response.raise_for_status()

    fetched_item = AlexaListItemOut.parse_obj(response.json())
    assert fetched_item == alexa_list_item


def test_alexa_crud_get_invalid_list_item(
    api_client: TestClient, user_linked: User, alexa_lists_with_items: list[AlexaListOut]
):
    # TODO: uncomment when incorrect list handling is done
    # response = api_client.get(
    #     alexa.api_router.url_path_for("get_list_item", list_id=random_string(), item_id=random_string()),
    #     headers=get_auth_headers(user_linked),
    # )
    # assert response.status_code == 404

    alexa_list = random.choice(alexa_lists_with_items)
    response = api_client.get(
        alexa.api_router.url_path_for("get_list_item", list_id=alexa_list.list_id, item_id=random_string()),
        headers=get_auth_headers(user_linked),
    )
    assert response.status_code == 404


def test_alexa_crud_get_list_item_unlinked(
    api_client: TestClient, user_linked_mealie: User, alexa_lists_with_items: list[AlexaListOut]
):
    alexa_list = random.choice(alexa_lists_with_items)
    assert alexa_list.items
    alexa_list_item = random.choice(alexa_list.items)

    response = api_client.get(
        alexa.api_router.url_path_for("get_list_item", list_id=alexa_list.list_id, item_id=alexa_list_item.id),
        headers=get_auth_headers(user_linked_mealie),
    )
    assert response.status_code == 401


def test_alexa_crud_create_list_item(
    alexa_list_service: AlexaListService,
    api_client: TestClient,
    user_linked: User,
    alexa_lists_with_items: list[AlexaListOut],
):
    alexa_list = random.choice(alexa_lists_with_items)
    item_to_create = AlexaListItemCreateIn(value=random_string())
    response = api_client.post(
        alexa.api_router.url_path_for("create_list_item", list_id=alexa_list.list_id),
        json=item_to_create.dict(),
        headers=get_auth_headers(user_linked),
    )
    response.raise_for_status()

    new_item = AlexaListItemOut.parse_obj(response.json())
    assert new_item.value == item_to_create.value

    fetched_list = alexa_list_service.get_list(alexa_list.list_id)
    assert fetched_list.items
    assert new_item in fetched_list.items


def test_alexa_crud_create_list_item_unlinked(
    api_client: TestClient, user_linked_mealie: User, alexa_lists_with_items: list[AlexaListOut]
):
    alexa_list = random.choice(alexa_lists_with_items)
    item_to_create = AlexaListItemCreateIn(value=random_string())
    response = api_client.post(
        alexa.api_router.url_path_for("create_list_item", list_id=alexa_list.list_id),
        json=item_to_create.dict(),
        headers=get_auth_headers(user_linked_mealie),
    )
    assert response.status_code == 401


def test_alexa_crud_create_list_items(
    alexa_list_service: AlexaListService,
    api_client: TestClient,
    user_linked: User,
    alexa_lists_with_items: list[AlexaListOut],
):
    alexa_list = random.choice(alexa_lists_with_items)
    items_to_create = [AlexaListItemCreateIn(value=random_string()) for _ in range(random_int(10, 20))]
    response = api_client.post(
        alexa.api_router.url_path_for("create_list_items", list_id=alexa_list.list_id),
        json=[item.dict() for item in items_to_create],
        headers=get_auth_headers(user_linked),
    )
    response.raise_for_status()

    new_items = AlexaListItemCollectionOut.parse_obj(response.json())
    assert len(new_items.list_items) == len(items_to_create)

    # check that all values are present and order is preserved
    for item_to_create, new_item in zip(items_to_create, new_items.list_items):
        assert item_to_create.value == new_item.value

    fetched_list = alexa_list_service.get_list(alexa_list.list_id)
    assert fetched_list.items
    for new_item in new_items.list_items:
        assert new_item in fetched_list.items


def test_alexa_crud_create_list_items_unlinked(
    api_client: TestClient, user_linked_mealie: User, alexa_lists_with_items: list[AlexaListOut]
):
    alexa_list = random.choice(alexa_lists_with_items)
    items_to_create = [AlexaListItemCreateIn(value=random_string()) for _ in range(random_int(10, 20))]
    response = api_client.post(
        alexa.api_router.url_path_for("create_list_items", list_id=alexa_list.list_id),
        json=[item.dict() for item in items_to_create],
        headers=get_auth_headers(user_linked_mealie),
    )
    assert response.status_code == 401


def test_alexa_crud_update_list_item(
    alexa_list_service: AlexaListService,
    api_client: TestClient,
    user_linked: User,
    alexa_lists_with_items: list[AlexaListOut],
):
    original_list = random.choice(alexa_lists_with_items)
    assert original_list.items
    original_item = random.choice(original_list.items)

    item_to_update = AlexaListItemUpdateIn(value=random_string())
    response = api_client.put(
        alexa.api_router.url_path_for("update_list_item", list_id=original_list.list_id, item_id=original_item.id),
        json=item_to_update.dict(),
        headers=get_auth_headers(user_linked),
    )
    response.raise_for_status()
    updated_item = AlexaListItemOut.parse_obj(response.json())

    # verify the item was properly updated
    assert original_item.value != item_to_update.value
    assert item_to_update.value == updated_item.value
    assert original_item.version == updated_item.version - 1

    # verify the list has both the changed and unchanged items
    fetched_list = alexa_list_service.get_list(original_list.list_id)
    assert fetched_list.items
    for fetched_item in fetched_list.items:
        if fetched_item.id == updated_item.id:
            assert fetched_item == updated_item
        else:
            assert fetched_item in original_list.items


def test_alexa_crud_update_list_item_unlinked(
    api_client: TestClient, user_linked_mealie: User, alexa_lists_with_items: list[AlexaListOut]
):
    original_list = random.choice(alexa_lists_with_items)
    assert original_list.items
    original_item = random.choice(original_list.items)

    item_to_update = AlexaListItemUpdateIn(id=original_item.id, value=random_string())
    response = api_client.put(
        alexa.api_router.url_path_for("update_list_item", list_id=original_list.list_id, item_id=original_item.id),
        json=item_to_update.dict(),
        headers=get_auth_headers(user_linked_mealie),
    )
    assert response.status_code == 401


def test_alexa_crud_update_list_items(
    alexa_list_service: AlexaListService,
    api_client: TestClient,
    user_linked: User,
    alexa_lists_with_items: list[AlexaListOut],
):
    original_list = random.choice(alexa_lists_with_items)
    assert original_list.items
    original_items = random.sample(original_list.items, 5)

    items_to_update = [
        AlexaListItemUpdateBulkIn(id=original_item.id, value=random_string()) for original_item in original_items
    ]
    response = api_client.put(
        alexa.api_router.url_path_for("update_list_items", list_id=original_list.list_id),
        json=[item.dict() for item in items_to_update],
        headers=get_auth_headers(user_linked),
    )
    response.raise_for_status()
    updated_items = AlexaListItemCollectionOut.parse_obj(response.json())

    original_items_by_id = {original_item.id: original_item for original_item in original_items}
    items_to_update_by_id = {item_to_update.id: item_to_update for item_to_update in items_to_update}
    updated_items_by_id = {updated_item.id: updated_item for updated_item in updated_items.list_items}
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


def test_alexa_crud_update_list_items_unlinked(
    api_client: TestClient, user_linked_mealie: User, alexa_lists_with_items: list[AlexaListOut]
):
    original_list = random.choice(alexa_lists_with_items)
    assert original_list.items
    original_items = random.sample(original_list.items, 5)

    items_to_update = [
        AlexaListItemUpdateBulkIn(id=original_item.id, value=random_string()) for original_item in original_items
    ]
    response = api_client.put(
        alexa.api_router.url_path_for("update_list_items", list_id=original_list.list_id),
        json=[item.dict() for item in items_to_update],
        headers=get_auth_headers(user_linked_mealie),
    )
    assert response.status_code == 401
