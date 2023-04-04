import random

import pytest

from AppLambda.src.clients.mealie import MealieClient
from AppLambda.src.models.mealie import AuthToken
from tests.utils import random_url


@pytest.fixture()
def mealie_client(mealie_api_tokens: list[AuthToken]) -> MealieClient:
    api_token = random.choice(mealie_api_tokens)
    return MealieClient(random_url(), api_token.token)
