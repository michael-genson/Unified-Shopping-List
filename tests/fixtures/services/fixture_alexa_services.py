import pytest

from AppLambda.src.models.core import User
from AppLambda.src.services.alexa import AlexaListService


@pytest.fixture()
def alexa_list_service(user_linked: User):
    service = AlexaListService(user_linked)
    yield service
    service._clear_cache()
