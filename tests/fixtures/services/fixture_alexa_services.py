import pytest

from AppLambda.src.models.core import User
from AppLambda.src.services.alexa import AlexaListService


@pytest.fixture()
def alexa_list_service(user_linked: User):
    service = AlexaListService(user_linked)
    yield service
    service.get_all_lists.cache_clear()
