import time
from functools import wraps
from inspect import iscoroutinefunction
from typing import Callable

from fastapi import HTTPException, status

from ..config import RATE_LIMIT_MINUTELY_MODIFY, RATE_LIMIT_MINUTELY_READ, RATE_LIMIT_MINUTELY_SYNC
from ..models.aws import DynamoDBAtomicOp
from ..models.core import RateLimitCategory, RateLimitInterval, User, UserRateLimit
from .user import UserService


class RateLimitService:
    def __init__(self, user_service: UserService) -> None:
        self.user_service = user_service

    @classmethod
    def get_limit(cls, category: RateLimitCategory, interval: RateLimitInterval = RateLimitInterval.minutely) -> int:
        """Returns the rate limit for a particular category + interval"""

        if interval != RateLimitInterval.minutely:
            raise NotImplementedError("Only minutely rate limits are supported")

        if category == RateLimitCategory.read:
            return RATE_LIMIT_MINUTELY_READ

        if category == RateLimitCategory.modify:
            return RATE_LIMIT_MINUTELY_MODIFY

        if category == RateLimitCategory.sync:
            return RATE_LIMIT_MINUTELY_SYNC

        raise NotImplementedError(f"Invalid RateLimitCategory {category}")

    def get_current_user_limit_value(self, user: User, category: RateLimitCategory) -> int:
        """Returns the user's rate limit value, or 0 if it's expired or undefined"""

        if not user.rate_limit_map or category.value not in user.rate_limit_map:
            return 0

        # rate limit has expired, so we consider it 0
        if round(time.time()) >= user.rate_limit_map[category.value].expires:
            return 0

        # return the stored value
        return user.rate_limit_map[category.value].value

    def check_if_user_limit_expired(self, user: User, category: RateLimitCategory) -> bool:
        if not user.rate_limit_map or category.value not in user.rate_limit_map:
            return False

        return round(time.time()) >= user.rate_limit_map[category.value].expires

    def verify_rate_limit(self, user: User, category: RateLimitCategory) -> None:
        """Updates the rate limit for a particular user and raises an HTTP 429 exception if the rate limit is violated"""

        if user.disabled or user.is_rate_limit_exempt:
            return

        # all rate limits are minutely - if this changes, we need to build that logic here
        rate_limit_interval_seconds = 60

        user_limit_value = self.get_current_user_limit_value(user, category)
        if user_limit_value >= self.get_limit(category):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded")

        # the user has not violated the rate limit, so we update their rate limit status
        # if the value is 0, then we write a new expiration, too
        if not user_limit_value:
            new_expires = round(time.time()) + rate_limit_interval_seconds

            # we need to write a brand-new rate limit map to the user
            if not user.rate_limit_map or category.value not in user.rate_limit_map:
                if not user.rate_limit_map:
                    user.rate_limit_map = {}

                # value is 1 since this API call is the first one
                user.rate_limit_map[category.value] = UserRateLimit(value=1, expires=new_expires)
                self.user_service.update_user(user)

            # we can overwrite the existing rate limit map
            else:
                user.rate_limit_map[category.value] = UserRateLimit(value=1, expires=new_expires)
                self.user_service.update_rate_limit(
                    user=user,
                    category=category,
                    operation=DynamoDBAtomicOp.overwrite,
                    value=1,
                    new_expires=new_expires,
                )

        # if the value is anything other than 0, we increment it
        else:
            user.rate_limit_map[category.value].value += 1  # type: ignore
            self.user_service.update_rate_limit(user, category, DynamoDBAtomicOp.increment)

    def limit(self, category: RateLimitCategory):
        """
        Rate limits a user based on their rate limit configuration. Use as a decorator under the FastAPI router.

        Throws an HTTP 429 exception if the rate limit is violated

        To use this in a method, rather than as a decorator, see `verify_rate_limit`
        """

        def rate_limit_handler(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                user = None
                if "user" in kwargs and isinstance(kwargs["user"], User):
                    user = kwargs["user"]

                if not user:
                    # check args for user
                    for arg in args:
                        if isinstance(arg, User):
                            user = arg
                            break

                if not user:
                    # check kwargs for user
                    for val in kwargs.values():
                        if isinstance(val, User):
                            user = val
                            break

                if not user:
                    raise ValueError(f"Unable to rate limit {func}; no user provided")

                self.verify_rate_limit(user, category)
                if iscoroutinefunction(func):
                    return await func(*args, **kwargs)

                else:
                    return func(*args, **kwargs)

            return wrapper

        return rate_limit_handler
