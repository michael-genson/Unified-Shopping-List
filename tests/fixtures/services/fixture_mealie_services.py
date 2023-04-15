import pytest

from AppLambda.src.models.account_linking import UserMealieConfigurationUpdate
from AppLambda.src.models.core import User
from AppLambda.src.services.mealie import MealieListService
from tests.utils.users import update_mealie_config


def _clear_mealie_list_service_cache(service: MealieListService) -> None:
    for cached_property in ["recipe_store", "food_store", "label_store"]:
        service.__dict__.pop(cached_property, None)

    service.get_food.cache_clear()
    service.get_label.cache_clear()
    service.get_all_lists.cache_clear()


@pytest.fixture()
def mealie_list_service(user_linked: User):
    assert user_linked.configuration.mealie
    config = user_linked.configuration.mealie.cast(UserMealieConfigurationUpdate)
    config.use_foods = False
    config.overwrite_original_item_names = False

    user = update_mealie_config(user_linked, config)
    service = MealieListService(user)
    yield service
    _clear_mealie_list_service_cache(service)


@pytest.fixture()
def mealie_list_service_use_foods(user_linked: User):
    assert user_linked.configuration.mealie
    config = user_linked.configuration.mealie.cast(UserMealieConfigurationUpdate)
    config.use_foods = True
    config.overwrite_original_item_names = False

    user = update_mealie_config(user_linked, config)
    service = MealieListService(user)
    yield service
    _clear_mealie_list_service_cache(service)


@pytest.fixture()
def mealie_list_service_overwrite_names(user_linked: User):
    assert user_linked.configuration.mealie
    config = user_linked.configuration.mealie.cast(UserMealieConfigurationUpdate)
    config.use_foods = True
    config.overwrite_original_item_names = True

    user = update_mealie_config(user_linked, config)
    service = MealieListService(user)
    yield service
    _clear_mealie_list_service_cache(service)
