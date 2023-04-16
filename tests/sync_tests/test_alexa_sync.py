import random

import pytest

from AppLambda.src.models.account_linking import UserMealieConfigurationUpdate
from AppLambda.src.models.alexa import (
    AlexaListItemCreateIn,
    AlexaListItemUpdateBulkIn,
    ListItemState,
    ObjectType,
    Operation,
)
from AppLambda.src.models.mealie import (
    Food,
    MealieEventType,
    MealieShoppingListItemCreate,
    MealieShoppingListItemUpdateBulk,
)
from AppLambda.src.services.alexa import AlexaListService
from AppLambda.src.services.mealie import MealieListService
from tests.fixtures.databases.alexa.mock_alexa_database import MockAlexaServer
from tests.fixtures.fixture_users import MockLinkedUserAndData
from tests.utils.event_handlers import (
    build_alexa_list_event,
    build_mealie_event_notification,
    send_alexa_list_event,
    send_mealie_event_notification,
)
from tests.utils.generators import random_int, random_string
from tests.utils.users import update_mealie_config


@pytest.mark.parametrize("use_foods, overwrite_names", [(False, False), (True, False), (True, True)])
def test_alexa_sync_created_items(
    use_foods: bool,
    overwrite_names: bool,
    mealie_list_service: MealieListService,
    alexa_list_service: AlexaListService,
    user_data: MockLinkedUserAndData,
    mealie_foods: list[Food],  # populate foods database
):
    user_data.user = update_mealie_config(
        user_data.user,
        UserMealieConfigurationUpdate(use_foods=use_foods, overwrite_original_item_names=overwrite_names),
    )
    mealie_list_service._clear_cache()

    # create items in Alexa
    new_items = [AlexaListItemCreateIn(value=random_string()) for _ in range(10)]
    created_items = alexa_list_service.create_list_items(user_data.alexa_list.list_id, new_items).list_items

    # send sync event
    event = build_alexa_list_event(
        Operation.create,
        ObjectType.list_item,
        list_id=user_data.alexa_list.list_id,
        list_item_ids=[item.id for item in created_items],
    )
    send_alexa_list_event(event, user_data.user)

    # verify new items are in Mealie
    for created_item in created_items:
        mealie_item = mealie_list_service.get_item_by_extra(user_data.mealie_list.id, "alexa_item_id", created_item.id)
        assert mealie_item
        assert mealie_item.display == created_item.value
        assert mealie_item.extras
        assert mealie_item.extras.alexa_item_id == created_item.id
        assert mealie_item.extras.alexa_item_version == "1"


@pytest.mark.parametrize("use_foods, overwrite_names", [(False, False), (True, False), (True, True)])
def test_alexa_sync_updated_items(
    use_foods: bool,
    overwrite_names: bool,
    mealie_list_service: MealieListService,
    alexa_list_service: AlexaListService,
    user_data: MockLinkedUserAndData,
    mealie_foods: list[Food],  # populate foods database
):
    user_data.user = update_mealie_config(
        user_data.user,
        UserMealieConfigurationUpdate(use_foods=use_foods, overwrite_original_item_names=overwrite_names),
    )
    mealie_list_service._clear_cache()

    # create items in Alexa
    new_items = [AlexaListItemCreateIn(value=random_string()) for _ in range(10)]
    created_items = alexa_list_service.create_list_items(user_data.alexa_list.list_id, new_items).list_items

    # send sync event
    event = build_alexa_list_event(
        Operation.create,
        ObjectType.list_item,
        list_id=user_data.alexa_list.list_id,
        list_item_ids=[item.id for item in created_items],
    )
    send_alexa_list_event(event, user_data.user)
    original_mealie_item_count = len(mealie_list_service.get_all_list_items(user_data.mealie_list.id))

    # update all items
    items_to_update = [item.cast(AlexaListItemUpdateBulkIn, value=random_string()) for item in created_items]
    updated_items = alexa_list_service.update_list_items(user_data.alexa_list.list_id, items_to_update).list_items

    # send sync event
    event = build_alexa_list_event(
        Operation.update,
        ObjectType.list_item,
        list_id=user_data.alexa_list.list_id,
        list_item_ids=[item.id for item in updated_items],
    )
    send_alexa_list_event(event, user_data.user)

    # verify items in Mealie were updated
    mealie_list_service._clear_cache()
    updated_mealie_item_count = len(mealie_list_service.get_all_list_items(user_data.mealie_list.id))
    assert updated_mealie_item_count == original_mealie_item_count

    for updated_item in updated_items:
        mealie_list_service._list_items_cache = {}
        mealie_item = mealie_list_service.get_item_by_extra(user_data.mealie_list.id, "alexa_item_id", updated_item.id)
        assert mealie_item
        assert mealie_item.display == updated_item.value
        assert mealie_item.extras
        assert mealie_item.extras.alexa_item_id == updated_item.id
        assert mealie_item.extras.alexa_item_version == "2"


@pytest.mark.parametrize("use_foods, overwrite_names", [(False, False), (True, False), (True, True)])
def test_alexa_sync_updated_items_old_version(
    use_foods: bool,
    overwrite_names: bool,
    mealie_list_service: MealieListService,
    alexa_list_service: AlexaListService,
    user_data: MockLinkedUserAndData,
    mealie_foods: list[Food],  # populate foods database
):
    user_data.user = update_mealie_config(
        user_data.user,
        UserMealieConfigurationUpdate(use_foods=use_foods, overwrite_original_item_names=overwrite_names),
    )
    mealie_list_service._clear_cache()

    # create items in Alexa
    new_items = [AlexaListItemCreateIn(value=random_string()) for _ in range(10)]
    created_items = alexa_list_service.create_list_items(user_data.alexa_list.list_id, new_items).list_items

    # send sync event
    event = build_alexa_list_event(
        Operation.create,
        ObjectType.list_item,
        list_id=user_data.alexa_list.list_id,
        list_item_ids=[item.id for item in created_items],
    )
    send_alexa_list_event(event, user_data.user)

    # update the versions on some items and make sure they aren't updated
    all_mealie_items = mealie_list_service.get_all_list_items(user_data.mealie_list.id)
    mealie_items_to_keep = random.sample(all_mealie_items, random_int(2, 5))
    mealie_items_to_update = [item.cast(MealieShoppingListItemUpdateBulk) for item in mealie_items_to_keep]
    for item in mealie_items_to_update:
        assert item.extras
        assert item.extras.alexa_item_version == "1"
        item.extras.alexa_item_version = "2"

    mealie_list_service.update_items(mealie_items_to_update)
    mealie_items_to_keep_by_alexa_id = {
        item.extras.alexa_item_id: item for item in mealie_items_to_keep if item.extras and item.extras.alexa_item_id
    }

    alexa_items_to_update = [item.cast(AlexaListItemUpdateBulkIn, value=random_string()) for item in created_items]
    updated_alexa_items = alexa_list_service.update_list_items(
        user_data.alexa_list.list_id, alexa_items_to_update
    ).list_items
    event = build_alexa_list_event(
        Operation.update,
        ObjectType.list_item,
        list_id=user_data.alexa_list.list_id,
        list_item_ids=[item.id for item in updated_alexa_items],
    )
    send_alexa_list_event(event, user_data.user)

    assert mealie_items_to_keep_by_alexa_id
    mealie_list_service._clear_cache()
    for updated_alexa_item in updated_alexa_items:
        mealie_list_service._list_items_cache = {}
        mealie_item = mealie_list_service.get_item_by_extra(
            user_data.mealie_list.id, "alexa_item_id", updated_alexa_item.id
        )
        assert mealie_item
        assert mealie_item.extras
        assert mealie_item.extras.alexa_item_id == updated_alexa_item.id
        assert mealie_item.extras.alexa_item_version and int(mealie_item.extras.alexa_item_version) > 1

        if mealie_item_to_keep := mealie_items_to_keep_by_alexa_id.pop(mealie_item.extras.alexa_item_id, None):
            assert mealie_item.id == mealie_item_to_keep.id
            assert mealie_item.display == mealie_item_to_keep.display
            assert mealie_item.display != updated_alexa_item.value
        else:
            assert mealie_item.display == updated_alexa_item.value

    assert not mealie_items_to_keep_by_alexa_id


@pytest.mark.parametrize("use_foods, overwrite_names", [(False, False), (True, False), (True, True)])
def test_alexa_sync_checked_items(
    use_foods: bool,
    overwrite_names: bool,
    mealie_list_service: MealieListService,
    alexa_list_service: AlexaListService,
    user_data: MockLinkedUserAndData,
    mealie_foods: list[Food],  # populate foods database
):
    user_data.user = update_mealie_config(
        user_data.user,
        UserMealieConfigurationUpdate(use_foods=use_foods, overwrite_original_item_names=overwrite_names),
    )
    mealie_list_service._clear_cache()

    # create items in Alexa
    new_items = [AlexaListItemCreateIn(value=random_string()) for _ in range(10)]
    created_alexa_items = alexa_list_service.create_list_items(user_data.alexa_list.list_id, new_items).list_items

    # send sync event
    event = build_alexa_list_event(
        Operation.create,
        ObjectType.list_item,
        list_id=user_data.alexa_list.list_id,
        list_item_ids=[item.id for item in created_alexa_items],
    )
    send_alexa_list_event(event, user_data.user)
    original_mealie_item_count = len(mealie_list_service.get_all_list_items(user_data.mealie_list.id))

    # check off some items
    alexa_items_to_check_off = [
        item.cast(AlexaListItemUpdateBulkIn, status=ListItemState.completed)
        for item in random.sample(created_alexa_items, random_int(2, 5))
    ]
    checked_alexa_items = alexa_list_service.update_list_items(
        user_data.alexa_list.list_id, alexa_items_to_check_off
    ).list_items
    event = build_alexa_list_event(
        Operation.update,
        ObjectType.list_item,
        list_id=user_data.alexa_list.list_id,
        list_item_ids=[item.id for item in checked_alexa_items],
    )
    send_alexa_list_event(event, user_data.user)

    # verify Mealie doesn't have the checked items
    mealie_list_service._clear_cache()
    mealie_alexa_list_item_ids = {
        item.extras.alexa_item_id
        for item in mealie_list_service.get_all_list_items(user_data.mealie_list.id)
        if item.extras and item.extras.alexa_item_id
    }
    assert len(mealie_alexa_list_item_ids) == original_mealie_item_count - len(checked_alexa_items)

    created_alexa_item_ids = {item.id for item in created_alexa_items}
    checked_alexa_item_ids = {item.id for item in checked_alexa_items}
    for checked_item_id in checked_alexa_item_ids:
        assert checked_item_id in created_alexa_item_ids

    for item in created_alexa_items:
        if item.id in mealie_alexa_list_item_ids:
            assert item.id not in checked_alexa_item_ids
        else:
            assert item.id in checked_alexa_item_ids


@pytest.mark.parametrize("use_foods, overwrite_names", [(False, False), (True, False), (True, True)])
def test_alexa_sync_deleted_items(
    use_foods: bool,
    overwrite_names: bool,
    mealie_list_service: MealieListService,
    alexa_server: MockAlexaServer,
    alexa_list_service: AlexaListService,
    user_data: MockLinkedUserAndData,
    mealie_foods: list[Food],  # populate foods database
):
    user_data.user = update_mealie_config(
        user_data.user,
        UserMealieConfigurationUpdate(use_foods=use_foods, overwrite_original_item_names=overwrite_names),
    )
    mealie_list_service._clear_cache()

    # create items in Alexa
    new_items = [AlexaListItemCreateIn(value=random_string()) for _ in range(10)]
    created_alexa_items = alexa_list_service.create_list_items(user_data.alexa_list.list_id, new_items).list_items

    # send sync event
    event = build_alexa_list_event(
        Operation.create,
        ObjectType.list_item,
        list_id=user_data.alexa_list.list_id,
        list_item_ids=[item.id for item in created_alexa_items],
    )
    send_alexa_list_event(event, user_data.user)
    original_mealie_item_count = len(mealie_list_service.get_all_list_items(user_data.mealie_list.id))

    # delete some items
    alexa_deleted_items_by_id = {item.id: item for item in random.sample(created_alexa_items, random_int(2, 5))}
    alexa_server.db[user_data.alexa_list.list_id]["items"] = [
        item
        for item in alexa_server.db[user_data.alexa_list.list_id]["items"]
        if item["id"] not in alexa_deleted_items_by_id
    ]

    event = build_alexa_list_event(
        Operation.update,
        ObjectType.list_item,
        list_id=user_data.alexa_list.list_id,
        list_item_ids=list(alexa_deleted_items_by_id.keys()),
    )
    send_alexa_list_event(event, user_data.user)

    # verify Mealie doesn't have the deleted items
    mealie_list_service._clear_cache()
    mealie_alexa_list_item_ids = {
        item.extras.alexa_item_id
        for item in mealie_list_service.get_all_list_items(user_data.mealie_list.id)
        if item.extras and item.extras.alexa_item_id
    }
    assert len(mealie_alexa_list_item_ids) == original_mealie_item_count - len(alexa_deleted_items_by_id)

    created_alexa_item_ids = {item.id for item in created_alexa_items}
    for checked_item_id in alexa_deleted_items_by_id:
        assert checked_item_id in created_alexa_item_ids

    for item in created_alexa_items:
        if item.id in mealie_alexa_list_item_ids:
            assert item.id not in alexa_deleted_items_by_id
        else:
            assert item.id in alexa_deleted_items_by_id


@pytest.mark.parametrize("use_foods, overwrite_names", [(False, False), (True, False), (True, True)])
def test_alexa_sync_receive_created_items(
    use_foods: bool,
    overwrite_names: bool,
    mealie_list_service: MealieListService,
    alexa_list_service: AlexaListService,
    user_data_with_mealie_items: MockLinkedUserAndData,
):
    user_data_with_mealie_items.user = update_mealie_config(
        user_data_with_mealie_items.user,
        UserMealieConfigurationUpdate(use_foods=use_foods, overwrite_original_item_names=overwrite_names),
    )
    mealie_list_service._clear_cache()

    user = user_data_with_mealie_items.user
    mealie_list_id = user_data_with_mealie_items.mealie_list.id
    alexa_list_id = user_data_with_mealie_items.alexa_list.list_id
    original_mealie_item_count = len(mealie_list_service.get_all_list_items(mealie_list_id))

    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)

    mealie_list_service._clear_cache()
    updated_mealie_item_count = len(mealie_list_service.get_all_list_items(mealie_list_id))
    assert original_mealie_item_count == updated_mealie_item_count

    # verify new items match
    alexa_items = alexa_list_service.get_list(alexa_list_id)
    assert alexa_items.items
    assert len(alexa_items.items) == updated_mealie_item_count
    for alexa_item in alexa_items.items:
        mealie_item = mealie_list_service.get_item_by_extra(mealie_list_id, "alexa_item_id", alexa_item.id)

        assert mealie_item
        assert mealie_item.display == alexa_item.value
        assert mealie_item.extras
        assert mealie_item.extras.alexa_item_id == alexa_item.id
        assert mealie_item.extras.alexa_item_version == "1"
        assert alexa_item.version == 1


@pytest.mark.parametrize("use_foods, overwrite_names", [(False, False), (True, False), (True, True)])
def test_alexa_sync_receive_updated_items(
    use_foods: bool,
    overwrite_names: bool,
    mealie_list_service: MealieListService,
    alexa_list_service: AlexaListService,
    user_data_with_mealie_items: MockLinkedUserAndData,
):
    user_data_with_mealie_items.user = update_mealie_config(
        user_data_with_mealie_items.user,
        UserMealieConfigurationUpdate(use_foods=use_foods, overwrite_original_item_names=overwrite_names),
    )
    mealie_list_service._clear_cache()

    user = user_data_with_mealie_items.user
    mealie_list_id = user_data_with_mealie_items.mealie_list.id
    alexa_list_id = user_data_with_mealie_items.alexa_list.list_id

    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)

    original_alexa_list = alexa_list_service.get_list(alexa_list_id)
    assert original_alexa_list.items
    original_alexa_item_count = len(original_alexa_list.items)
    alexa_list_service._clear_cache()

    # update all items
    updated_mealie_items = mealie_list_service.get_all_list_items(mealie_list_id)
    mealie_list_service.update_items(
        [item.cast(MealieShoppingListItemUpdateBulk, note=random_string()) for item in updated_mealie_items]
    )
    mealie_list_service._clear_cache()

    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)

    # verify Alexa items match Mealie items
    updated_alexa_list = alexa_list_service.get_list(alexa_list_id)
    assert updated_alexa_list.items
    assert len(updated_alexa_list.items) == original_alexa_item_count

    for alexa_item in updated_alexa_list.items:
        mealie_item = mealie_list_service.get_item_by_extra(mealie_list_id, "alexa_item_id", alexa_item.id)

        assert mealie_item
        assert mealie_item.display == alexa_item.value
        assert mealie_item.extras
        assert mealie_item.extras.alexa_item_id == alexa_item.id
        assert mealie_item.extras.alexa_item_version == "2"
        assert alexa_item.version == 2


@pytest.mark.parametrize("use_foods, overwrite_names", [(False, False), (True, False), (True, True)])
def test_alexa_sync_receive_updated_item_old_version(
    use_foods: bool,
    overwrite_names: bool,
    mealie_list_service: MealieListService,
    alexa_list_service: AlexaListService,
    user_data_with_mealie_items: MockLinkedUserAndData,
):
    user_data_with_mealie_items.user = update_mealie_config(
        user_data_with_mealie_items.user,
        UserMealieConfigurationUpdate(use_foods=use_foods, overwrite_original_item_names=overwrite_names),
    )
    mealie_list_service._clear_cache()

    user = user_data_with_mealie_items.user
    mealie_list_id = user_data_with_mealie_items.mealie_list.id
    alexa_list_id = user_data_with_mealie_items.alexa_list.list_id

    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)

    # update some items on Alexa only to increment the version number
    all_alexa_items = alexa_list_service.get_list(alexa_list_id).items
    assert all_alexa_items
    alexa_items_to_update_version_by_id = {item.id: item for item in random.sample(all_alexa_items, random_int(2, 5))}
    alexa_list_service.update_list_items(
        alexa_list_id, [item.cast(AlexaListItemUpdateBulkIn) for item in alexa_items_to_update_version_by_id.values()]
    )
    alexa_list_service._clear_cache()

    # update all Mealie items and verify the higher-versioned Alexa items are not updated
    mealie_list_service.update_items(
        [
            item.cast(MealieShoppingListItemUpdateBulk, note=random_string())
            for item in mealie_list_service.get_all_list_items(mealie_list_id)
        ]
    )
    mealie_list_service._clear_cache()

    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)

    updated_alexa_list = alexa_list_service.get_list(alexa_list_id)
    assert updated_alexa_list.items
    assert alexa_items_to_update_version_by_id
    for alexa_item in updated_alexa_list.items:
        mealie_item = mealie_list_service.get_item_by_extra(mealie_list_id, "alexa_item_id", alexa_item.id)

        assert mealie_item
        assert mealie_item.extras
        assert mealie_item.extras.alexa_item_id == alexa_item.id
        assert alexa_item.version == 2
        # Since the event started from Mealie, Alexa won't write back the updated version to Mealie.
        # In practice, Alexa would fire a notification that its version had been updated, which would
        # trigger a sync to Mealie, but our test bypasses this since notifications are fired manually

        if alexa_item.id in alexa_items_to_update_version_by_id:
            unchanged_item = alexa_items_to_update_version_by_id.pop(alexa_item.id)
            assert alexa_item.value == unchanged_item.value
        else:
            # Since Alexa never called an update to Mealie, this is
            # only True for items which didn't have their versions updated.
            # In practice, another sync would have made the values line up
            assert mealie_item.display == alexa_item.value

    # make sure all unchanged items were found
    assert not alexa_items_to_update_version_by_id


@pytest.mark.parametrize("use_foods, overwrite_names", [(False, False), (True, False), (True, True)])
def test_alexa_sync_receive_checked_items(
    use_foods: bool,
    overwrite_names: bool,
    mealie_list_service: MealieListService,
    alexa_list_service: AlexaListService,
    user_data_with_mealie_items: MockLinkedUserAndData,
):
    user_data_with_mealie_items.user = update_mealie_config(
        user_data_with_mealie_items.user,
        UserMealieConfigurationUpdate(use_foods=use_foods, overwrite_original_item_names=overwrite_names),
    )
    mealie_list_service._clear_cache()

    user = user_data_with_mealie_items.user
    mealie_list_id = user_data_with_mealie_items.mealie_list.id
    alexa_list_id = user_data_with_mealie_items.alexa_list.list_id

    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)

    # check off some items
    new_mealie_items = mealie_list_service.get_all_list_items(mealie_list_id)
    mealie_items_to_check_off = random.sample(new_mealie_items, random_int(2, 5))
    mealie_list_service.update_items(
        [item.cast(MealieShoppingListItemUpdateBulk, checked=True) for item in mealie_items_to_check_off]
    )
    mealie_list_service._clear_cache()

    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)

    # verify Alexa doesn't have the checked items
    updated_alexa_items = alexa_list_service.get_list(alexa_list_id).items
    assert updated_alexa_items
    new_mealie_item_ids = {item.id for item in new_mealie_items}

    # fetching a list includes checked items
    for alexa_item in updated_alexa_items:
        if alexa_item.status == ListItemState.active.value:
            mealie_item = mealie_list_service.get_item_by_extra(mealie_list_id, "alexa_item_id", alexa_item.id)
            assert mealie_item
            new_mealie_item_ids.remove(mealie_item.id)
        else:
            assert not mealie_list_service.get_item_by_extra(mealie_list_id, "alexa_item_id", alexa_item.id)

    # the only item ids left should be the ones that were checked off, if we found the rest
    assert len(new_mealie_item_ids) == len(mealie_items_to_check_off)


@pytest.mark.parametrize("use_foods, overwrite_names", [(False, False), (True, False), (True, True)])
def test_alexa_sync_receive_created_and_updated_items(
    use_foods: bool,
    overwrite_names: bool,
    mealie_list_service: MealieListService,
    alexa_list_service: AlexaListService,
    user_data_with_mealie_items: MockLinkedUserAndData,
):
    user_data_with_mealie_items.user = update_mealie_config(
        user_data_with_mealie_items.user,
        UserMealieConfigurationUpdate(use_foods=use_foods, overwrite_original_item_names=overwrite_names),
    )
    mealie_list_service._clear_cache()

    user = user_data_with_mealie_items.user
    mealie_list_id = user_data_with_mealie_items.mealie_list.id
    alexa_list_id = user_data_with_mealie_items.alexa_list.list_id

    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)

    # update some existing items and create some new items
    mealie_list_service.update_items(
        [
            item.cast(MealieShoppingListItemUpdateBulk, note=random_string())
            for item in random.sample(mealie_list_service.get_all_list_items(mealie_list_id), random_int(3, 5))
        ]
    )

    mealie_list_service.create_items(
        [
            MealieShoppingListItemCreate(
                shopping_list_id=mealie_list_id,
                note=random_string(),
            )
            for _ in range(random_int(5, 10))
        ]
    )

    mealie_list_service._clear_cache()
    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)

    # verify Mealie matches Alexa
    alexa_items = alexa_list_service.get_list(alexa_list_id).items
    assert alexa_items
    mealie_items = mealie_list_service.get_all_list_items(mealie_list_id)
    assert len(mealie_items) == len(alexa_items)
    for alexa_item in alexa_items:
        mealie_item = mealie_list_service.get_item_by_extra(mealie_list_id, "alexa_item_id", alexa_item.id)

        assert mealie_item
        assert mealie_item.display == alexa_item.value
        assert mealie_item.extras
        assert mealie_item.extras.alexa_item_id == alexa_item.id


@pytest.mark.parametrize("use_foods, overwrite_names", [(False, False), (True, False), (True, True)])
def test_alexa_sync_full(
    use_foods: bool,
    overwrite_names: bool,
    mealie_list_service: MealieListService,
    alexa_list_service: AlexaListService,
    user_data_with_mealie_items: MockLinkedUserAndData,
):
    user_data_with_mealie_items.user = update_mealie_config(
        user_data_with_mealie_items.user,
        UserMealieConfigurationUpdate(use_foods=use_foods, overwrite_original_item_names=overwrite_names),
    )
    mealie_list_service._clear_cache()

    user = user_data_with_mealie_items.user
    mealie_list_id = user_data_with_mealie_items.mealie_list.id
    alexa_list_id = user_data_with_mealie_items.alexa_list.list_id

    # create Alexa items so we have new items in both systems
    new_items = [AlexaListItemCreateIn(value=random_string()) for _ in range(10)]
    created_items = alexa_list_service.create_list_items(alexa_list_id, new_items).list_items
    alexa_list_service._clear_cache()

    event = build_alexa_list_event(
        Operation.create,
        ObjectType.list_item,
        list_id=user_data_with_mealie_items.alexa_list.list_id,
        list_item_ids=[item.id for item in created_items],
    )
    send_alexa_list_event(event, user)

    all_alexa_items = alexa_list_service.get_list(alexa_list_id).items
    assert all_alexa_items
    all_mealie_items = mealie_list_service.get_all_list_items(mealie_list_id)
    assert len(all_mealie_items) == len(all_mealie_items)

    for alexa_item in all_alexa_items:
        mealie_item = mealie_list_service.get_item_by_extra(mealie_list_id, "alexa_item_id", alexa_item.id)

        assert mealie_item
        assert mealie_item.display == alexa_item.value
        assert mealie_item.extras
        assert mealie_item.extras.alexa_item_id == alexa_item.id
        assert mealie_item.extras.alexa_item_version == "1"
        assert alexa_item.version == 1
