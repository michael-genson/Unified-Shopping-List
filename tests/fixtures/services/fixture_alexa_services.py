import pytest

from AppLambda.src.models.core import User
from AppLambda.src.services.alexa import AlexaListService


@pytest.fixture()
def alexa_list_service(user_linked: User) -> AlexaListService:
    return AlexaListService(user_linked)
