import random

import pytest

from AppLambda.src.app import settings
from AppLambda.src.models.account_linking import UserMealieConfigurationUpdate, UserTodoistConfigurationUpdate
from AppLambda.src.models.mealie import (
    Food,
    Label,
    MealieEventType,
    MealieShoppingListItemCreate,
    MealieShoppingListItemUpdateBulk,
)
from AppLambda.src.models.todoist import TodoistEventType
from AppLambda.src.services.mealie import MealieListService
from AppLambda.src.services.todoist import TodoistTaskService
from tests.fixtures.fixture_users import MockLinkedUserAndData
from tests.utils.event_handlers import (
    build_mealie_event_notification,
    build_todoist_webhook,
    send_mealie_event_notification,
    send_todoist_webhook,
)
from tests.utils.generators import random_int, random_string
from tests.utils.users import update_mealie_config, update_todoist_config


@pytest.mark.parametrize("use_foods, overwrite_names", [(False, False), (True, False), (True, True)])
def test_todoist_sync_created_items(
    use_foods: bool,
    overwrite_names: bool,
    mealie_list_service: MealieListService,
    todoist_task_service: TodoistTaskService,
    user_data: MockLinkedUserAndData,
    mealie_foods: list[Food],  # populate foods database
    mealie_labels: list[Label],
):
    user_data.user = update_mealie_config(
        user_data.user,
        UserMealieConfigurationUpdate(use_foods=use_foods, overwrite_original_item_names=overwrite_names),
    )
    user_data.user = update_todoist_config(
        user_data.user, UserTodoistConfigurationUpdate(map_labels_to_sections=use_foods)
    )
    mealie_list_service._clear_cache()
    todoist_task_service._clear_cache()
    assert user_data.user.todoist_user_id

    # create tasks in Todoist
    for _ in range(5):
        todoist_task_service.add_task(
            content=random_string(),
            project_id=user_data.todoist_data.project.id,
            section=random.choice(mealie_labels).name,
        )

        todoist_task_service.add_task(
            content=random_string(),
            project_id=user_data.todoist_data.project.id,
        )

    # send sync event
    webhook = build_todoist_webhook(
        TodoistEventType.item_added, user_data.user.todoist_user_id, user_data.todoist_data.project.id
    )
    send_todoist_webhook(webhook)

    # verify new items are in Mealie
    todoist_task_service._clear_cache()
    tasks = todoist_task_service.get_tasks(user_data.todoist_data.project.id)
    mealie_items = mealie_list_service.get_all_list_items(user_data.mealie_list.id)
    assert len(tasks) == len(mealie_items)

    for task in tasks:
        mealie_item = mealie_list_service.get_item_by_extra(user_data.mealie_list.id, "todoist_task_id", task.id)

        assert mealie_item
        assert mealie_item.display == task.content
        assert mealie_item.extras
        assert mealie_item.extras.todoist_task_id == task.id
        assert settings.todoist_mealie_label in task.labels

        # when configured, tasks with no section will be given a default section
        assert bool(task.section_id) is use_foods
        should_have_label = (
            use_foods
            and task.section_id
            and not todoist_task_service.is_default_section(task.section_id, user_data.todoist_data.project.id)
        )
        if not should_have_label:
            assert not mealie_item.label_id
            assert not mealie_item.label
        else:
            assert mealie_item.label_id
            assert mealie_item.label

            assert task.section_id
            todoist_section = todoist_task_service.get_section_by_id(task.section_id)
            assert mealie_item.label.name == todoist_section.name


@pytest.mark.parametrize("use_foods, overwrite_names", [(False, False), (True, False), (True, True)])
def test_todoist_sync_updated_items(
    use_foods: bool,
    overwrite_names: bool,
    mealie_list_service: MealieListService,
    todoist_task_service: TodoistTaskService,
    user_data: MockLinkedUserAndData,
    mealie_foods: list[Food],  # populate foods database
    mealie_labels: list[Label],
):
    user_data.user = update_mealie_config(
        user_data.user,
        UserMealieConfigurationUpdate(use_foods=use_foods, overwrite_original_item_names=overwrite_names),
    )
    user_data.user = update_todoist_config(
        user_data.user, UserTodoistConfigurationUpdate(map_labels_to_sections=use_foods)
    )
    mealie_list_service._clear_cache()
    todoist_task_service._clear_cache()
    assert user_data.user.todoist_user_id

    # create tasks in Todoist and sync them over to Mealie
    for _ in range(5):
        todoist_task_service.add_task(
            content=random_string(),
            project_id=user_data.todoist_data.project.id,
            section=random.choice(mealie_labels).name,
        )

        todoist_task_service.add_task(
            content=random_string(),
            project_id=user_data.todoist_data.project.id,
        )

    webhook = build_todoist_webhook(
        TodoistEventType.item_added, user_data.user.todoist_user_id, user_data.todoist_data.project.id
    )
    send_todoist_webhook(webhook)
    todoist_task_service._clear_cache()

    # update all tasks and verify changes propagate
    original_mealie_item_count = len(mealie_list_service.get_all_list_items(user_data.mealie_list.id))
    mealie_list_service._clear_cache()
    original_tasks_by_id = {task.id: task for task in todoist_task_service.get_tasks(user_data.todoist_data.project.id)}
    for original_task in original_tasks_by_id.values():
        todoist_task_service.update_task(original_task.id, original_task.project_id, content=random_string())

    webhook = build_todoist_webhook(
        TodoistEventType.item_updated, user_data.user.todoist_user_id, user_data.todoist_data.project.id
    )
    send_todoist_webhook(webhook)
    todoist_task_service._clear_cache()

    updated_mealie_item_count = len(mealie_list_service.get_all_list_items(user_data.mealie_list.id))
    assert updated_mealie_item_count == original_mealie_item_count
    updated_tasks = todoist_task_service.get_tasks(user_data.todoist_data.project.id)
    for task in updated_tasks:
        mealie_item = mealie_list_service.get_item_by_extra(user_data.mealie_list.id, "todoist_task_id", task.id)

        assert mealie_item
        assert mealie_item.display == task.content != original_tasks_by_id[task.id].content
        assert mealie_item.extras
        assert mealie_item.extras.todoist_task_id == task.id
        assert settings.todoist_mealie_label in task.labels

        assert task.section_id == original_tasks_by_id[task.id].section_id
        should_have_label = (
            use_foods
            and task.section_id
            and not todoist_task_service.is_default_section(task.section_id, user_data.todoist_data.project.id)
        )
        if not should_have_label:
            assert not mealie_item.label_id
            assert not mealie_item.label
        else:
            assert mealie_item.label_id
            assert mealie_item.label

            assert task.section_id
            todoist_section = todoist_task_service.get_section_by_id(task.section_id)
            assert mealie_item.label.name == todoist_section.name


@pytest.mark.parametrize("use_foods, overwrite_names", [(False, False), (True, False), (True, True)])
def test_todoist_sync_updated_item_section(
    use_foods: bool,
    overwrite_names: bool,
    mealie_list_service: MealieListService,
    todoist_task_service: TodoistTaskService,
    user_data: MockLinkedUserAndData,
    mealie_foods: list[Food],  # populate foods database
    mealie_labels: list[Label],
):
    user_data.user = update_mealie_config(
        user_data.user,
        UserMealieConfigurationUpdate(use_foods=use_foods, overwrite_original_item_names=overwrite_names),
    )
    user_data.user = update_todoist_config(
        user_data.user, UserTodoistConfigurationUpdate(map_labels_to_sections=use_foods)
    )
    mealie_list_service._clear_cache()
    todoist_task_service._clear_cache()
    assert user_data.user.todoist_user_id

    # create tasks in Todoist and sync them over to Mealie
    for _ in range(5):
        todoist_task_service.add_task(
            content=random_string(),
            project_id=user_data.todoist_data.project.id,
            section=random.choice(mealie_labels).name,
        )

        todoist_task_service.add_task(
            content=random_string(),
            project_id=user_data.todoist_data.project.id,
        )

    webhook = build_todoist_webhook(
        TodoistEventType.item_added, user_data.user.todoist_user_id, user_data.todoist_data.project.id
    )
    send_todoist_webhook(webhook)
    todoist_task_service._clear_cache()

    # update the content and section on all tasks and verify Mealie has the expected label
    original_mealie_item_count = len(mealie_list_service.get_all_list_items(user_data.mealie_list.id))
    mealie_list_service._clear_cache()

    original_tasks = todoist_task_service.get_tasks(user_data.todoist_data.project.id)
    for task in original_tasks:
        todoist_task_service.update_task(task.id, task.project_id, section=random.choice(mealie_labels).name)

    webhook = build_todoist_webhook(
        TodoistEventType.item_updated, user_data.user.todoist_user_id, user_data.todoist_data.project.id
    )
    send_todoist_webhook(webhook)
    todoist_task_service._clear_cache()

    # we don't compare to the original Todoist tasks because task ids may change
    updated_mealie_item_count = len(mealie_list_service.get_all_list_items(user_data.mealie_list.id))
    assert updated_mealie_item_count == original_mealie_item_count

    updated_tasks = todoist_task_service.get_tasks(user_data.todoist_data.project.id)
    assert len(updated_tasks) == len(original_tasks)
    for task in updated_tasks:
        mealie_item = mealie_list_service.get_item_by_extra(user_data.mealie_list.id, "todoist_task_id", task.id)

        assert mealie_item
        assert mealie_item.display == task.content

        assert bool(task.section_id) is use_foods
        should_have_label = (
            use_foods
            and task.section_id
            and not todoist_task_service.is_default_section(task.section_id, user_data.todoist_data.project.id)
        )
        if not should_have_label:
            assert not mealie_item.label_id
            assert not mealie_item.label
        else:
            assert mealie_item.label_id
            assert mealie_item.label

            assert task.section_id
            todoist_section = todoist_task_service.get_section_by_id(task.section_id)
            assert mealie_item.label.name == todoist_section.name


@pytest.mark.parametrize("use_foods, overwrite_names", [(False, False), (True, False), (True, True)])
def test_todoist_sync_checked_items(
    use_foods: bool,
    overwrite_names: bool,
    mealie_list_service: MealieListService,
    todoist_task_service: TodoistTaskService,
    user_data: MockLinkedUserAndData,
    mealie_foods: list[Food],  # populate foods database
    mealie_labels: list[Label],
):
    user_data.user = update_mealie_config(
        user_data.user,
        UserMealieConfigurationUpdate(use_foods=use_foods, overwrite_original_item_names=overwrite_names),
    )
    user_data.user = update_todoist_config(
        user_data.user, UserTodoistConfigurationUpdate(map_labels_to_sections=use_foods)
    )
    mealie_list_service._clear_cache()
    todoist_task_service._clear_cache()
    assert user_data.user.todoist_user_id

    # create tasks in Todoist and sync them over to Mealie
    for _ in range(5):
        todoist_task_service.add_task(
            content=random_string(),
            project_id=user_data.todoist_data.project.id,
            section=random.choice(mealie_labels).name,
        )

        todoist_task_service.add_task(
            content=random_string(),
            project_id=user_data.todoist_data.project.id,
        )

    webhook = build_todoist_webhook(
        TodoistEventType.item_added, user_data.user.todoist_user_id, user_data.todoist_data.project.id
    )
    send_todoist_webhook(webhook)
    todoist_task_service._clear_cache()

    # check off some of them and verify they're removed from Mealie
    original_mealie_item_count = len(mealie_list_service.get_all_list_items(user_data.mealie_list.id))
    mealie_list_service._clear_cache()

    tasks_to_check_off = random.sample(
        todoist_task_service.get_tasks(user_data.todoist_data.project.id), random_int(2, 5)
    )
    for task in tasks_to_check_off:
        todoist_task_service.close_task(task)

    webhook = build_todoist_webhook(
        TodoistEventType.item_added, user_data.user.todoist_user_id, user_data.todoist_data.project.id
    )
    send_todoist_webhook(webhook)
    todoist_task_service._clear_cache()

    updated_mealie_items = mealie_list_service.get_all_list_items(user_data.mealie_list.id)
    updated_todoist_tasks = todoist_task_service.get_tasks(user_data.todoist_data.project.id)
    assert (
        len(updated_mealie_items) == len(updated_todoist_tasks) == original_mealie_item_count - len(tasks_to_check_off)
    )

    for task in updated_todoist_tasks:
        mealie_item = mealie_list_service.get_item_by_extra(user_data.mealie_list.id, "todoist_task_id", task.id)
        assert mealie_item

    for task in tasks_to_check_off:
        mealie_item = mealie_list_service.get_item_by_extra(user_data.mealie_list.id, "todoist_task_id", task.id)
        assert not mealie_item


@pytest.mark.parametrize("use_foods, overwrite_names", [(False, False), (True, False), (True, True)])
def test_todoist_sync_created_and_updated_items(
    use_foods: bool,
    overwrite_names: bool,
    mealie_list_service: MealieListService,
    todoist_task_service: TodoistTaskService,
    user_data: MockLinkedUserAndData,
    mealie_foods: list[Food],  # populate foods database
    mealie_labels: list[Label],
):
    user_data.user = update_mealie_config(
        user_data.user,
        UserMealieConfigurationUpdate(use_foods=use_foods, overwrite_original_item_names=overwrite_names),
    )
    user_data.user = update_todoist_config(
        user_data.user, UserTodoistConfigurationUpdate(map_labels_to_sections=use_foods)
    )
    mealie_list_service._clear_cache()
    todoist_task_service._clear_cache()
    assert user_data.user.todoist_user_id

    # create tasks in Todoist and sync them over to Mealie
    for _ in range(10):
        todoist_task_service.add_task(
            content=random_string(),
            project_id=user_data.todoist_data.project.id,
            section=random.choice(mealie_labels).name,
        )

    webhook = build_todoist_webhook(
        TodoistEventType.item_added, user_data.user.todoist_user_id, user_data.todoist_data.project.id
    )
    send_todoist_webhook(webhook)
    todoist_task_service._clear_cache()

    # update all tasks and create new tasks
    for task in todoist_task_service.get_tasks(user_data.todoist_data.project.id):
        todoist_task_service.update_task(task.id, user_data.todoist_data.project.id, content=random_string())

    for _ in range(10):
        todoist_task_service.add_task(
            content=random_string(),
            project_id=user_data.todoist_data.project.id,
            section=random.choice(mealie_labels).name,
        )

    webhook = build_todoist_webhook(
        TodoistEventType.item_added, user_data.user.todoist_user_id, user_data.todoist_data.project.id
    )
    send_todoist_webhook(webhook)
    todoist_task_service._clear_cache()

    # verify Mealie items are synced correctly
    for task in todoist_task_service.get_tasks(user_data.todoist_data.project.id):
        mealie_item = mealie_list_service.get_item_by_extra(user_data.mealie_list.id, "todoist_task_id", task.id)

        assert mealie_item
        assert mealie_item.display == task.content
        assert mealie_item.extras
        assert mealie_item.extras.todoist_task_id == task.id
        assert settings.todoist_mealie_label in task.labels


@pytest.mark.parametrize("use_sections, use_descriptions", [(False, False), (True, False), (False, True), (True, True)])
def test_todoist_sync_receive_created_items(
    use_sections: bool,
    use_descriptions: bool,
    mealie_list_service: MealieListService,
    todoist_task_service: TodoistTaskService,
    user_data_with_mealie_items: MockLinkedUserAndData,
):
    user_data_with_mealie_items.user = update_mealie_config(
        user_data_with_mealie_items.user,
        UserMealieConfigurationUpdate(use_foods=use_sections),
    )
    user_data_with_mealie_items.user = update_todoist_config(
        user_data_with_mealie_items.user,
        UserTodoistConfigurationUpdate(
            map_labels_to_sections=use_sections, add_recipes_to_task_description=use_descriptions
        ),
    )
    mealie_list_service._clear_cache()
    todoist_task_service._clear_cache()

    user = user_data_with_mealie_items.user
    mealie_list_id = user_data_with_mealie_items.mealie_list.id
    project_id = user_data_with_mealie_items.todoist_data.project.id
    assert user.todoist_user_id

    original_mealie_item_count = len(mealie_list_service.get_all_list_items(mealie_list_id))

    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)
    mealie_list_service._clear_cache()

    updated_mealie_item_count = len(mealie_list_service.get_all_list_items(mealie_list_id))
    assert original_mealie_item_count == updated_mealie_item_count
    tasks = todoist_task_service.get_tasks(project_id)
    assert len(tasks) == updated_mealie_item_count

    for task in tasks:
        mealie_item = mealie_list_service.get_item_by_extra(mealie_list_id, "todoist_task_id", task.id)

        assert mealie_item
        assert mealie_item.display == task.content
        assert mealie_item.extras
        assert mealie_item.extras.todoist_task_id == task.id
        assert settings.todoist_mealie_label in task.labels

        should_have_description = use_descriptions and mealie_item.recipe_references
        if should_have_description:
            assert task.description
        else:
            assert not task.description

        should_have_section = use_sections and mealie_item.label
        if should_have_section:
            assert mealie_item.label
            assert task.section_id
            assert todoist_task_service.get_section_by_id(task.section_id).name == mealie_item.label.name
        else:
            assert not task.section_id


@pytest.mark.parametrize("use_sections, use_descriptions", [(False, False), (True, False), (False, True), (True, True)])
def test_todoist_sync_receive_updated_items(
    use_sections: bool,
    use_descriptions: bool,
    mealie_list_service: MealieListService,
    todoist_task_service: TodoistTaskService,
    user_data_with_mealie_items: MockLinkedUserAndData,
):
    user_data_with_mealie_items.user = update_mealie_config(
        user_data_with_mealie_items.user,
        UserMealieConfigurationUpdate(use_foods=use_sections),
    )
    user_data_with_mealie_items.user = update_todoist_config(
        user_data_with_mealie_items.user,
        UserTodoistConfigurationUpdate(
            map_labels_to_sections=use_sections, add_recipes_to_task_description=use_descriptions
        ),
    )
    mealie_list_service._clear_cache()
    todoist_task_service._clear_cache()

    user = user_data_with_mealie_items.user
    mealie_list_id = user_data_with_mealie_items.mealie_list.id
    project_id = user_data_with_mealie_items.todoist_data.project.id
    assert user.todoist_user_id

    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)
    mealie_list_service._clear_cache()

    # update all items
    items_to_update = [
        item.cast(MealieShoppingListItemUpdateBulk, note=random_string())
        for item in mealie_list_service.get_all_list_items(mealie_list_id)
    ]
    mealie_list_service.update_items(items_to_update)
    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)
    mealie_list_service._clear_cache()

    # verify Todoist tasks match Mealie
    mealie_item_count = len(mealie_list_service.get_all_list_items(mealie_list_id))
    tasks = todoist_task_service.get_tasks(project_id)
    assert len(tasks) == mealie_item_count
    for task in tasks:
        mealie_item = mealie_list_service.get_item_by_extra(mealie_list_id, "todoist_task_id", task.id)

        assert mealie_item
        assert mealie_item.display == task.content
        assert mealie_item.extras
        assert mealie_item.extras.todoist_task_id == task.id
        assert settings.todoist_mealie_label in task.labels

        should_have_description = use_descriptions and mealie_item.recipe_references
        if should_have_description:
            assert task.description
        else:
            assert not task.description

        should_have_section = use_sections and mealie_item.label
        if should_have_section:
            assert mealie_item.label
            assert task.section_id
            assert todoist_task_service.get_section_by_id(task.section_id).name == mealie_item.label.name
        else:
            assert not task.section_id


@pytest.mark.parametrize("use_sections, use_descriptions", [(False, False), (True, False), (False, True), (True, True)])
def test_todoist_sync_receive_updated_item_label(
    use_sections: bool,
    use_descriptions: bool,
    mealie_list_service: MealieListService,
    todoist_task_service: TodoistTaskService,
    user_data_with_mealie_items: MockLinkedUserAndData,
    mealie_labels: list[Label],
):
    user_data_with_mealie_items.user = update_mealie_config(
        user_data_with_mealie_items.user,
        UserMealieConfigurationUpdate(use_foods=use_sections),
    )
    user_data_with_mealie_items.user = update_todoist_config(
        user_data_with_mealie_items.user,
        UserTodoistConfigurationUpdate(
            map_labels_to_sections=use_sections, add_recipes_to_task_description=use_descriptions
        ),
    )
    mealie_list_service._clear_cache()
    todoist_task_service._clear_cache()

    user = user_data_with_mealie_items.user
    mealie_list_id = user_data_with_mealie_items.mealie_list.id
    project_id = user_data_with_mealie_items.todoist_data.project.id
    assert user.todoist_user_id

    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)
    mealie_list_service._clear_cache()

    # update the labels on all items and verify the sections change in Todoist
    items_to_update = [
        item.cast(MealieShoppingListItemUpdateBulk, label_id=random.choice(mealie_labels).id)
        for item in mealie_list_service.get_all_list_items(mealie_list_id)
    ]
    mealie_list_service.update_items(items_to_update)

    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)
    mealie_list_service._clear_cache()

    all_items = mealie_list_service.get_all_list_items(mealie_list_id)
    all_tasks = todoist_task_service.get_tasks(project_id)
    assert len(all_items) == len(all_tasks)
    for task in all_tasks:
        mealie_item = mealie_list_service.get_item_by_extra(mealie_list_id, "todoist_task_id", task.id)

        assert mealie_item
        should_have_section = use_sections and mealie_item.label
        if should_have_section:
            assert mealie_item.label
            assert task.section_id
            assert todoist_task_service.get_section_by_id(task.section_id).name == mealie_item.label.name
        else:
            assert not task.section_id


@pytest.mark.parametrize("use_sections, use_descriptions", [(False, False), (True, False), (False, True), (True, True)])
def test_todoist_sync_receive_checked_items(
    use_sections: bool,
    use_descriptions: bool,
    mealie_list_service: MealieListService,
    todoist_task_service: TodoistTaskService,
    user_data_with_mealie_items: MockLinkedUserAndData,
):
    user_data_with_mealie_items.user = update_mealie_config(
        user_data_with_mealie_items.user,
        UserMealieConfigurationUpdate(use_foods=use_sections),
    )
    user_data_with_mealie_items.user = update_todoist_config(
        user_data_with_mealie_items.user,
        UserTodoistConfigurationUpdate(
            map_labels_to_sections=use_sections, add_recipes_to_task_description=use_descriptions
        ),
    )
    mealie_list_service._clear_cache()
    todoist_task_service._clear_cache()

    user = user_data_with_mealie_items.user
    mealie_list_id = user_data_with_mealie_items.mealie_list.id
    project_id = user_data_with_mealie_items.todoist_data.project.id
    assert user.todoist_user_id

    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)
    mealie_list_service._clear_cache()

    # check off some items and verify they're no longer in Todoist
    original_mealie_items = mealie_list_service.get_all_list_items(mealie_list_id)
    items_to_check = [
        item.cast(MealieShoppingListItemUpdateBulk, checked=True)
        for item in random.sample(original_mealie_items, random_int(2, 5))
    ]
    mealie_list_service.update_items(items_to_check)

    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)
    mealie_list_service._clear_cache()

    updated_mealie_items = mealie_list_service.get_all_list_items(mealie_list_id)
    tasks = todoist_task_service.get_tasks(project_id)
    assert len(updated_mealie_items) == len(tasks) == len(original_mealie_items) - len(items_to_check)

    for task in tasks:
        assert mealie_list_service.get_item_by_extra(mealie_list_id, "todoist_task_id", task.id)

    for checked_item in items_to_check:
        assert checked_item.extras
        todoist_task_id = checked_item.extras.todoist_task_id
        assert todoist_task_id
        assert not todoist_task_service.get_task(todoist_task_id, project_id)


@pytest.mark.parametrize("use_sections, use_descriptions", [(False, False), (True, False), (False, True), (True, True)])
def test_todoist_sync_receive_mixed_items(
    use_sections: bool,
    use_descriptions: bool,
    mealie_list_service: MealieListService,
    todoist_task_service: TodoistTaskService,
    user_data_with_mealie_items: MockLinkedUserAndData,
):
    user_data_with_mealie_items.user = update_mealie_config(
        user_data_with_mealie_items.user,
        UserMealieConfigurationUpdate(use_foods=use_sections),
    )
    user_data_with_mealie_items.user = update_todoist_config(
        user_data_with_mealie_items.user,
        UserTodoistConfigurationUpdate(
            map_labels_to_sections=use_sections, add_recipes_to_task_description=use_descriptions
        ),
    )
    mealie_list_service._clear_cache()
    todoist_task_service._clear_cache()

    user = user_data_with_mealie_items.user
    mealie_list_id = user_data_with_mealie_items.mealie_list.id
    project_id = user_data_with_mealie_items.todoist_data.project.id
    assert user.todoist_user_id

    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)
    mealie_list_service._clear_cache()

    # update all Mealie items and create some new ones
    mealie_list_service.update_items(
        [
            item.cast(MealieShoppingListItemUpdateBulk, note=random_string())
            for item in mealie_list_service.get_all_list_items(mealie_list_id)
        ]
    )
    mealie_list_service.create_items(
        [MealieShoppingListItemCreate(shopping_list_id=mealie_list_id, note=random_string()) for _ in range(10)]
    )

    event = build_mealie_event_notification(MealieEventType.shopping_list_updated, mealie_list_id)
    send_mealie_event_notification(event, user)
    mealie_list_service._clear_cache()

    all_mealie_items = mealie_list_service.get_all_list_items(mealie_list_id)
    tasks = todoist_task_service.get_tasks(project_id)
    assert len(all_mealie_items) == len(tasks)

    for task in tasks:
        mealie_item = mealie_list_service.get_item_by_extra(mealie_list_id, "todoist_task_id", task.id)

        assert mealie_item
        assert mealie_item.display == task.content
        assert mealie_item.extras
        assert mealie_item.extras.todoist_task_id == task.id
        assert settings.todoist_mealie_label in task.labels


def test_todoist_full_sync(
    mealie_list_service: MealieListService,
    todoist_task_service: TodoistTaskService,
    user_data_with_mealie_items: MockLinkedUserAndData,
):
    user = user_data_with_mealie_items.user
    mealie_list_id = user_data_with_mealie_items.mealie_list.id
    project_id = user_data_with_mealie_items.todoist_data.project.id
    assert user.todoist_user_id

    # create tasks in Todoist
    for _ in range(10):
        todoist_task_service.add_task(
            content=random_string(),
            project_id=project_id,
        )

    original_mealie_item_count = len(mealie_list_service.get_all_list_items(mealie_list_id))
    original_todoist_task_count = len(todoist_task_service.get_tasks(project_id))

    # send sync event and compare item lists
    webhook = build_todoist_webhook(TodoistEventType.item_added, user.todoist_user_id, project_id)
    send_todoist_webhook(webhook)
    mealie_list_service._clear_cache()
    todoist_task_service._clear_cache()

    updated_mealie_items = mealie_list_service.get_all_list_items(mealie_list_id)
    updated_tasks = todoist_task_service.get_tasks(project_id)
    assert len(updated_mealie_items) == len(updated_tasks) == original_mealie_item_count + original_todoist_task_count

    for task in updated_tasks:
        mealie_item = mealie_list_service.get_item_by_extra(mealie_list_id, "todoist_task_id", task.id)

        assert mealie_item
        assert mealie_item.display == task.content
        assert mealie_item.extras
        assert mealie_item.extras.todoist_task_id == task.id
        assert settings.todoist_mealie_label in task.labels
