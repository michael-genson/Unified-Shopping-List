import pytest

from AppLambda.src.models.account_linking import UserMealieConfigurationUpdate
from AppLambda.src.models.core import User
from AppLambda.src.services.mealie import MealieListService
from tests.utils.users import update_mealie_config


@pytest.fixture()
def mealie_list_service(user_linked: User):
    return MealieListService(user_linked)


@pytest.fixture()
def mealie_list_service_use_foods(user_linked: User):
    assert user_linked.configuration.mealie
    config = user_linked.configuration.mealie.cast(UserMealieConfigurationUpdate)
    config.use_foods = True
    config.overwrite_original_item_names = False

    user = update_mealie_config(user_linked, config)
    return MealieListService(user)


@pytest.fixture()
def mealie_list_service_overwrite_names(user_linked: User):
    assert user_linked.configuration.mealie
    config = user_linked.configuration.mealie.cast(UserMealieConfigurationUpdate)
    config.use_foods = True
    config.overwrite_original_item_names = True

    user = update_mealie_config(user_linked, config)
    return MealieListService(user)
