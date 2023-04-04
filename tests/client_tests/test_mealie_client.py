import random

from AppLambda.src.clients.mealie import MealieClient
from AppLambda.src.models.mealie import AuthToken
from tests.fixtures.databases.mealie.router import MockDBKey, MockMealieServer
from tests.utils import random_string


def test_mealie_client_is_valid(mealie_client: MealieClient):
    assert mealie_client.is_valid

    # reach into the mealie client and make its auth token invalid
    mealie_client.client._client.headers["Authorization"] = f"Bearer {random_string()}"
    assert not mealie_client.is_valid


def test_mealie_client_create_auth_token(mealie_server: MockMealieServer, mealie_client: MealieClient):
    existing_auth_token_data = mealie_server.get_all_records(MockDBKey.user_api_tokens)
    existing_auth_tokens = [AuthToken(**data) for data in existing_auth_token_data.values()]

    new_token = mealie_client.create_auth_token(random_string())
    updated_auth_token_data = mealie_server.get_all_records(MockDBKey.user_api_tokens)
    updated_auth_tokens = [AuthToken(**data) for data in updated_auth_token_data.values()]

    assert len(updated_auth_tokens) == len(existing_auth_tokens) + 1
    assert [new_token] == [token for token in updated_auth_tokens if token not in existing_auth_tokens]


def test_mealie_client_delete_auth_token(
    mealie_server: MockMealieServer, mealie_client: MealieClient, mealie_api_tokens: list[AuthToken]
):
    existing_auth_token_data = mealie_server.get_all_records(MockDBKey.user_api_tokens)
    existing_auth_tokens = [AuthToken(**data) for data in existing_auth_token_data.values()]

    token_to_delete = random.choice(mealie_api_tokens)
    mealie_client.delete_auth_token(token_to_delete.id)

    updated_auth_token_data = mealie_server.get_all_records(MockDBKey.user_api_tokens)
    updated_auth_tokens = [AuthToken(**data) for data in updated_auth_token_data.values()]

    assert len(updated_auth_tokens) == len(existing_auth_tokens) - 1
    assert [token_to_delete] == [token for token in existing_auth_tokens if token not in updated_auth_tokens]
