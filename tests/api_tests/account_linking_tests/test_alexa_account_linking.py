from fastapi.testclient import TestClient

from AppLambda.src.models.account_linking import UserAlexaConfiguration
from AppLambda.src.models.core import User
from AppLambda.src.routes import account_linking
from AppLambda.src.services.auth_token import AuthTokenService
from AppLambda.src.services.user import UserService
from tests.utils import get_auth_headers, random_string


def test_alexa_link_create(
    token_service: AuthTokenService, user_service: UserService, api_client: TestClient, user_linked_mealie: User
):
    alexa_user_id = random_string()
    params = {"userId": alexa_user_id}
    response = api_client.post(
        account_linking.api_router.url_path_for("link_alexa_account"),
        params=params,
        headers=get_auth_headers(token_service, user_linked_mealie),
    )
    response.raise_for_status()
    new_config = UserAlexaConfiguration.parse_obj(response.json())
    assert new_config.is_valid

    # confirm the user is updated
    updated_user = user_service.get_user(user_linked_mealie.username)
    assert updated_user
    assert updated_user.is_linked_to_alexa
    assert updated_user.configuration.alexa == new_config
    assert updated_user.alexa_user_id == alexa_user_id


def test_alexa_link_delete(
    token_service: AuthTokenService, user_service: UserService, api_client: TestClient, user_linked: User
):
    assert user_linked.is_linked_to_alexa
    response = api_client.delete(
        account_linking.api_router.url_path_for("unlink_alexa_account"),
        headers=get_auth_headers(token_service, user_linked),
    )
    response.raise_for_status()

    # verify user is no longer linked to alexa
    updated_user = user_service.get_user(user_linked.username)
    assert updated_user
    assert not updated_user.is_linked_to_alexa
    assert not updated_user.configuration.alexa

    # verify user is still linked to mealie
    assert updated_user.is_linked_to_mealie
    assert updated_user.configuration.mealie
