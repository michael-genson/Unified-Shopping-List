import pytest

from AppLambda.src.models.core import User
from AppLambda.src.services.mealie import MealieListService


@pytest.fixture()
def mealie_list_service(user_linked: User):
    return MealieListService(user_linked)


@pytest.fixture()
def mealie_list_service_use_foods(user_linked_use_foods: User):
    return MealieListService(user_linked_use_foods)


@pytest.fixture()
def mealie_list_service_overwrite_names(user_linked_overwrite_names: User):
    return MealieListService(user_linked_overwrite_names)
