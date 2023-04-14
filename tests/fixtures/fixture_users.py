import random

from fastapi.testclient import TestClient
from pytest import fixture

from AppLambda.src.models.alexa import AlexaListOut
from AppLambda.src.models.core import ListSyncMap, User
from AppLambda.src.models.mealie import AuthToken, MealieShoppingListOut
from AppLambda.src.routes import account_linking
from AppLambda.src.services.user import UserService
from tests.fixtures.databases.todoist.fixture_todoist_database import MockTodoistData

from ..utils.generators import random_string, random_url
from ..utils.users import create_user_with_known_credentials, get_auth_headers


class MockLinkedUserAndData:
    def __init__(
        self, user: User, mealie_list: MealieShoppingListOut, alexa_list: AlexaListOut, todoist_data: MockTodoistData
    ) -> None:
        self.user = user
        self.mealie_list = mealie_list
        self.alexa_list = alexa_list
        self.todoist_data = todoist_data


@fixture()
def user(api_client: TestClient) -> User:
    user, _ = create_user_with_known_credentials(api_client)
    return user.cast(User)


@fixture()
def user_linked_mealie(
    user_service: UserService, api_client: TestClient, user: User, mealie_api_tokens: list[AuthToken]
) -> User:
    """User that is only linked to Mealie"""

    api_token = random.choice(mealie_api_tokens)
    params = {"baseUrl": random_url(), "initialAuthToken": api_token.token}
    response = api_client.post(
        account_linking.api_router.url_path_for("link_mealie_account"),
        params=params,
        headers=get_auth_headers(user),
    )
    response.raise_for_status()

    linked_user = user_service.get_user(user.username)
    assert linked_user
    return linked_user.cast(User)


@fixture()
def user_linked(user_service: UserService, api_client: TestClient, user_linked_mealie: User) -> User:
    """User that is linked to all services"""

    # link user to Alexa
    params = {"userId": random_string()}
    response = api_client.post(
        account_linking.api_router.url_path_for("link_alexa_account"),
        params=params,
        headers=get_auth_headers(user_linked_mealie),
    )
    response.raise_for_status()

    # link user to Todoist
    params = {"accessToken": random_string()}
    response = api_client.post(
        account_linking.api_router.url_path_for("link_todoist_account"),
        params=params,
        headers=get_auth_headers(user_linked_mealie),
    )
    response.raise_for_status()

    linked_user = user_service.get_user(user_linked_mealie.username)
    assert linked_user
    return linked_user.cast(User)


@fixture()
def user_data(
    user_service: UserService,
    user_linked: User,
    mealie_shopping_lists_no_items: list[MealieShoppingListOut],
    alexa_lists_with_no_items: list[AlexaListOut],
    todoist_data_no_tasks: list[MockTodoistData],
) -> MockLinkedUserAndData:
    """
    User that is linked to all services, has pre-populated lists
    with no list items, and has a list sync map connecting each list
    """

    mealie_list = random.choice(mealie_shopping_lists_no_items)
    alexa_list = random.choice(alexa_lists_with_no_items)
    todoist_data_single = random.choice(todoist_data_no_tasks)

    # link all lists together
    user_linked.list_sync_maps = {
        mealie_list.id: ListSyncMap(
            mealie_shopping_list_id=mealie_list.id,
            alexa_list_id=alexa_list.list_id,
            todoist_project_id=todoist_data_single.project.id,
        )
    }
    user_service.update_user(user_linked)
    user_out = user_service.get_user(user_linked.username)
    assert user_out
    user = user_out.cast(User)

    return MockLinkedUserAndData(
        user=user,
        mealie_list=mealie_list,
        alexa_list=alexa_list,
        todoist_data=todoist_data_single,
    )


@fixture()
def user_data_with_items(
    user_service: UserService,
    user_linked: User,
    mealie_shopping_lists_with_foods_labels_units_recipe: list[MealieShoppingListOut],
    alexa_lists_with_items: list[AlexaListOut],
    todoist_data: list[MockTodoistData],
) -> MockLinkedUserAndData:
    """
    User that is linked to all services, has pre-populated lists
    and list items, and has a list sync map connecting each list
    """

    mealie_list = random.choice(mealie_shopping_lists_with_foods_labels_units_recipe)
    alexa_list = random.choice(alexa_lists_with_items)
    todoist_data_single = random.choice(todoist_data)

    # link all lists together
    user_linked.list_sync_maps = {
        mealie_list.id: ListSyncMap(
            mealie_shopping_list_id=mealie_list.id,
            alexa_list_id=alexa_list.list_id,
            todoist_project_id=todoist_data_single.project.id,
        )
    }
    user_service.update_user(user_linked)
    user_out = user_service.get_user(user_linked.username)
    assert user_out
    user = user_out.cast(User)

    return MockLinkedUserAndData(
        user=user,
        mealie_list=mealie_list,
        alexa_list=alexa_list,
        todoist_data=todoist_data_single,
    )
