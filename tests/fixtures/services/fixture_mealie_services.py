import pytest

from AppLambda.src.models.core import User
from AppLambda.src.services.mealie import MealieListService


@pytest.fixture()
def mealie_list_service(user_linked_mealie: User):
    return MealieListService(user_linked_mealie)


@pytest.fixture()
def mealie_list_service_use_foods(user_linked_mealie_use_foods: User):
    return MealieListService(user_linked_mealie_use_foods)


@pytest.fixture()
def mealie_list_service_overwrite_names(user_linked_mealie_overwrite_names: User):
    return MealieListService(user_linked_mealie_overwrite_names)
