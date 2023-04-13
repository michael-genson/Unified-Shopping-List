from fastapi.testclient import TestClient

from AppLambda.src.models.account_linking import UserTodoistConfiguration
from AppLambda.src.models.core import User
from AppLambda.src.routes import account_linking
from AppLambda.src.services.auth_token import AuthTokenService
from AppLambda.src.services.user import UserService
from tests.fixtures.databases.todoist.mock_todoist_api import MockTodoistAPI
from tests.utils.generators import random_bool, random_string
from tests.utils.users import get_auth_headers


def test_todoist_link_create(
    token_service: AuthTokenService,
    user_service: UserService,
    todoist_api: MockTodoistAPI,
    api_client: TestClient,
    user_linked_mealie: User,
):
    assert not user_linked_mealie.is_linked_to_todoist

    # get the current state of all projects, sections, and tasks
    all_projects = todoist_api.get_projects()
    all_sections = todoist_api.get_sections()
    all_tasks = todoist_api.get_tasks()

    params = {"accessToken": random_string()}
    response = api_client.post(
        account_linking.api_router.url_path_for("link_todoist_account"),
        params=params,
        headers=get_auth_headers(token_service, user_linked_mealie),
    )
    response.raise_for_status()

    new_config = UserTodoistConfiguration.parse_obj(response.json())
    user = user_service.get_user(user_linked_mealie.username)
    assert user
    assert user.is_linked_to_todoist
    assert user.todoist_user_id
    assert user.configuration.todoist == new_config
    assert user.configuration.todoist.is_valid

    # make sure there are no changes in projects, sections, or tasks
    assert todoist_api.get_projects() == all_projects
    assert todoist_api.get_sections() == all_sections
    assert todoist_api.get_tasks() == all_tasks


def test_todoist_link_update(
    token_service: AuthTokenService,
    user_service: UserService,
    api_client: TestClient,
    user_linked: User,
):
    existing_config = user_linked.configuration.todoist
    assert existing_config

    params: dict = {
        "mapLabelsToSections": not existing_config.map_labels_to_sections,
        "defaultSectionName": existing_config.default_section_name,
        "addRecipesToTaskDescription": existing_config.add_recipes_to_task_description,
    }
    response = api_client.put(
        account_linking.api_router.url_path_for("update_todoist_account_link"),
        params=params,
        headers=get_auth_headers(token_service, user_linked),
    )
    response.raise_for_status()

    updated_user = user_service.get_user(user_linked.username)
    assert updated_user

    assert updated_user.is_linked_to_todoist
    updated_config = updated_user.configuration.todoist
    assert updated_config

    assert updated_config.map_labels_to_sections is not None
    assert updated_config.map_labels_to_sections is not bool(existing_config.map_labels_to_sections)
    assert updated_config.default_section_name == existing_config.default_section_name
    assert updated_config.add_recipes_to_task_description == existing_config.add_recipes_to_task_description


def test_todoist_link_update_not_linked(
    token_service: AuthTokenService, user_service: UserService, api_client: TestClient, user_linked_mealie: User
):
    assert not user_linked_mealie.is_linked_to_todoist

    params: dict = {
        "mapLabelsToSections": random_bool(),
        "defaultSectionName": random_string(),
        "addRecipesToTaskDescription": random_bool(),
    }
    response = api_client.put(
        account_linking.api_router.url_path_for("update_todoist_account_link"),
        params=params,
        headers=get_auth_headers(token_service, user_linked_mealie),
    )
    assert response.status_code == 401

    updated_user = user_service.get_user(user_linked_mealie.username)
    assert updated_user
    assert not updated_user.is_linked_to_todoist
    assert not updated_user.configuration.todoist


def test_todoist_link_delete(
    token_service: AuthTokenService, user_service: UserService, api_client: TestClient, user_linked: User
):
    assert user_linked.is_linked_to_todoist
    response = api_client.delete(
        account_linking.api_router.url_path_for("unlink_todoist_account"),
        headers=get_auth_headers(token_service, user_linked),
    )
    response.raise_for_status()

    # verify user is no longer linked to todoist
    updated_user = user_service.get_user(user_linked.username)
    assert updated_user
    assert not updated_user.is_linked_to_todoist
    assert not updated_user.configuration.todoist
