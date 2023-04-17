import pytest

from AppLambda.src.models.account_linking import UserTodoistConfigurationUpdate
from AppLambda.src.models.core import User
from AppLambda.src.services.todoist import TodoistTaskService
from tests.utils.users import update_todoist_config


@pytest.fixture()
def todoist_task_service(user_linked: User):
    assert user_linked.configuration.todoist
    config = user_linked.configuration.todoist.cast(UserTodoistConfigurationUpdate)
    config.map_labels_to_sections = False
    config.add_recipes_to_task_description = False

    user = update_todoist_config(user_linked, config)
    service = TodoistTaskService(user)
    yield service
    service._clear_cache()


@pytest.fixture()
def todoist_task_service_use_sections(user_linked: User):
    assert user_linked.configuration.todoist
    config = user_linked.configuration.todoist.cast(UserTodoistConfigurationUpdate)
    config.map_labels_to_sections = True
    config.add_recipes_to_task_description = False

    user = update_todoist_config(user_linked, config)
    service = TodoistTaskService(user)
    yield service
    service._clear_cache()


@pytest.fixture()
def todoist_task_service_use_sections_and_descriptions(user_linked: User):
    assert user_linked.configuration.todoist
    config = user_linked.configuration.todoist.cast(UserTodoistConfigurationUpdate)
    config.map_labels_to_sections = True
    config.add_recipes_to_task_description = True

    user = update_todoist_config(user_linked, config)
    service = TodoistTaskService(user)
    yield service
    service._clear_cache()
