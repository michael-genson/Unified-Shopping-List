import random
import time
from datetime import datetime
from typing import Optional

import pytest
from fastapi import HTTPException
from freezegun import freeze_time

from AppLambda.src.models.core import RateLimitCategory, User, UserRateLimit
from AppLambda.src.services.rate_limit import RateLimitService
from AppLambda.src.services.user import UserService
from tests.utils import random_int

ALL_RATE_LIMIT_CATEGORIES = [RateLimitCategory.modify, RateLimitCategory.read, RateLimitCategory.sync]


def test_rate_limit_service_get_current_user_limit_value(rate_limit_service: RateLimitService, user: User):
    category = random.choice(ALL_RATE_LIMIT_CATEGORIES)
    assert rate_limit_service.get_current_user_limit_value(user, category) == 0

    new_value = random_int(1, 100)
    new_expires = time.time() + 999
    user.rate_limit_map = {category.value: UserRateLimit(value=new_value, expires=new_expires)}
    assert rate_limit_service.get_current_user_limit_value(user, category) == new_value

    # after the rate limit expires, it should come back as 0
    with freeze_time(datetime.fromtimestamp(new_expires + 10)):
        assert rate_limit_service.get_current_user_limit_value(user, category) == 0


def test_rate_limit_service_check_if_expired(rate_limit_service: RateLimitService, user: User):
    category = random.choice(ALL_RATE_LIMIT_CATEGORIES)
    user.rate_limit_map = {category.value: UserRateLimit(value=0, expires=time.time() + 999)}
    assert not rate_limit_service.check_if_user_limit_expired(user, category)

    user.rate_limit_map = {category.value: UserRateLimit(value=0, expires=time.time() - 999)}
    assert rate_limit_service.check_if_user_limit_expired(user, category)

    # missing rate limit maps are considered not expired
    user.rate_limit_map = None
    assert not rate_limit_service.check_if_user_limit_expired(user, category)

    user.rate_limit_map = {}
    assert not rate_limit_service.check_if_user_limit_expired(user, category)


def test_rate_limit_service_verify_rate_limit(
    rate_limit_service: RateLimitService, user_service: UserService, user: Optional[User]
):
    assert user
    category = random.choice(ALL_RATE_LIMIT_CATEGORIES)
    limit = rate_limit_service.get_limit(category)

    user.rate_limit_map = None
    user_service.update_user(user)
    rate_limit_service.verify_rate_limit(user, category)
    user = user_service.get_user(user.username)
    assert user
    assert user.rate_limit_map
    assert user.rate_limit_map[category.value].value > 0

    user.rate_limit_map = {category.value: UserRateLimit(value=0, expires=time.time() + 999)}
    user_service.update_user(user)
    rate_limit_service.verify_rate_limit(user, category)
    user = user_service.get_user(user.username)
    assert user
    assert user.rate_limit_map
    assert user.rate_limit_map[category.value].value > 0

    # if the user is one below the limit, they should be okay
    user.rate_limit_map = {category.value: UserRateLimit(value=limit - 1, expires=time.time() + 999)}
    user_service.update_user(user)
    rate_limit_service.verify_rate_limit(user, category)
    user = user_service.get_user(user.username)
    assert user
    assert user.rate_limit_map
    assert user.rate_limit_map[category.value].value > limit - 1

    # user violated rate limit
    with pytest.raises(HTTPException) as e_info:
        user.rate_limit_map = {category.value: UserRateLimit(value=limit, expires=time.time() + 999)}
        user_service.update_user(user)
        rate_limit_service.verify_rate_limit(user, category)

    assert e_info.value.status_code == 429

    with pytest.raises(HTTPException) as e_info:
        user.rate_limit_map = {category.value: UserRateLimit(value=limit + 999, expires=time.time() + 999)}
        user_service.update_user(user)
        rate_limit_service.verify_rate_limit(user, category)

    assert e_info.value.status_code == 429

    # disabled and exempt users have no effect
    user.disabled = True
    new_map = {category.value: UserRateLimit(value=limit + 999, expires=time.time() - 999)}
    user.rate_limit_map = new_map
    user_service.update_user(user)
    rate_limit_service.verify_rate_limit(user, category)
    user = user_service.get_user(user.username, active_only=False)
    assert user
    assert user.rate_limit_map == new_map

    user.disabled = False
    user.is_rate_limit_exempt = True
    user.rate_limit_map = new_map
    user_service.update_user(user)
    rate_limit_service.verify_rate_limit(user, category)
    user = user_service.get_user(user.username)
    assert user
    assert user.rate_limit_map == new_map
