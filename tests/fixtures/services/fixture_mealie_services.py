import pytest

from AppLambda.src.models.core import User
from AppLambda.src.services.mealie import MealieListService


@pytest.fixture()
def mealie_list_service(user_linked_mealie: User):
    return MealieListService(user_linked_mealie)
