import contextlib
import random
import time
from collections import defaultdict

import pytest

from AppLambda.src import config
from AppLambda.src.models.aws import DynamoDBAtomicOp
from AppLambda.src.models.core import RateLimitCategory, User, UserRateLimit, WhitelistError
from AppLambda.src.services.auth_token import AuthTokenService
from AppLambda.src.services.user import (
    UserAlreadyExistsError,
    UserIsDisabledError,
    UserIsNotRegisteredError,
    UserService,
)
from tests.utils.generators import random_email, random_int, random_password, random_string


@pytest.fixture()
def user_service() -> UserService:
    token_service = AuthTokenService()
    return UserService(token_service)


def test_get_user(user_service: UserService):
    # active user
    username = random_email()
    user_service.create_new_user(
        username=username,
        email=username,
        password=random_password(),
        disabled=False,
        create_registration_token=False,
    )

    user = user_service.get_user(username, active_only=True)
    assert user
    assert not user.disabled
    assert user.username == username

    user = user_service.get_user(username, active_only=False)
    assert user
    assert not user.disabled
    assert user.username == username

    # case insensitive
    assert user_service.get_user(username.upper(), active_only=False)

    # inactive user
    username = random_email()
    user_service.create_new_user(
        username=username,
        email=username,
        password=random_password(),
        disabled=True,
        create_registration_token=False,
    )

    user = user_service.get_user(username, active_only=True)
    assert not user

    user = user_service.get_user(username, active_only=False)
    assert user
    assert user.disabled
    assert user.username == username

    # invalid user
    response = user_service.get_user(random_email(), active_only=False)
    assert not response


def test_delete_user(user_service: UserService, user: User):
    assert user_service.get_user(user.username, active_only=True)
    user_service.delete_user(user.username)
    assert not user_service.get_user(user.username, active_only=True)

    # this shouldn't raise an error even though the user doesn't exist
    user_service.delete_user(user.username)
    assert not user_service.get_user(user.username, active_only=True)


def test_get_usernames_by_secondary_index(user_service: UserService):
    secondary_index = random.choice(["alexa_user_id", "todoist_user_id"])

    usernames: defaultdict[int, set[str]] = defaultdict(set)
    index_values: dict[int, str] = {}

    # create various users with common secondary index values
    for i in range(random_int(3, 5)):
        index_values[i] = random_string()
        for _ in range(random_int(3, 5)):
            username = random_email()
            usernames[i].add(username)

            user = user_service.create_new_user(
                username=username,
                email=username,
                password=random_password(),
                disabled=False,
                create_registration_token=False,
            )
            setattr(user, secondary_index, index_values[i])
            user_service.update_user(user)

    # verify we fetch the correct subset of users
    for i, username_set in usernames.items():
        fetched_usernames = user_service.get_usernames_by_secondary_index(secondary_index, index_values[i])
        for username in fetched_usernames:
            assert username in username_set


def test_authenticate_user(user_service: UserService):
    username = random_email()
    password = random_password()
    user_service.create_new_user(username=username, email=username, password=password, disabled=False)

    user = user_service.get_user(username)
    assert user

    response = user_service.get_authenticated_user(username, random_password())
    assert not response
    authenticated_user = user_service.get_authenticated_user(username, password)
    assert authenticated_user


def test_get_authenticated_user(user_service: UserService):
    username = random_email()
    password = random_password()
    user_service.create_new_user(username=username, email=username, password=password, disabled=False)

    response = user_service.get_authenticated_user(username, random_password())
    assert not response
    authenticated_user = user_service.get_authenticated_user(username, password)
    assert authenticated_user

    # case insensitive
    assert user_service.get_authenticated_user(username.upper(), password)

    # create disabled user
    username = random_email()
    password = random_password()
    user = user_service.create_new_user(username=username, email=username, password=password, disabled=True)

    # with expiration
    with pytest.raises(UserIsNotRegisteredError):
        user_service.get_authenticated_user(username, password)

    # without expiration
    user_service.update_user(user, remove_expiration=True)
    with pytest.raises(UserIsDisabledError):
        user_service.get_authenticated_user(username, password)

    # create user and enable whitelist
    username = random_email()
    password = random_password()
    user_service.create_new_user(username=username, email=username, password=password, disabled=False)

    config.USE_WHITELIST = True
    with pytest.raises(WhitelistError):
        user_service.get_authenticated_user(username, password)


def test_create_user(user_service: UserService):
    username = random_email()
    new_user = user_service.create_new_user(
        username=username,
        email=username,
        password=random_password(),
        disabled=False,
        create_registration_token=False,
    )

    user = user_service.get_user(username)
    assert user and user.cast(User) == new_user

    # verify username and email are sanitized
    username = random_email()
    new_user = user_service.create_new_user(
        username=username.upper() + " ",
        email=username.upper() + " ",
        password=random_password(),
        disabled=False,
        create_registration_token=False,
    )

    user = user_service.get_user(username)
    assert user
    assert user.username == username == username.lower()
    assert user.email == username == username.lower()

    # raise exception if an active user already exists
    with pytest.raises(UserAlreadyExistsError):
        user_service.create_new_user(
            username=username,
            email=username,
            password=random_password(),
        )

    # make sure the user is unchanged
    user = user_service.get_user(user.username)
    assert user and user.cast(User) == new_user

    # allow replacing a disabled user with a new user
    user.disabled = True
    user_service.update_user(user)

    replacement_user = user_service.create_new_user(
        username=username,
        email=username,
        password=random_password(),
    )

    assert replacement_user != new_user

    # check that a registration token is generated when appropriate
    username = random_email()
    new_user = user_service.create_new_user(
        username=username,
        email=username,
        password=random_password(),
        disabled=False,
        create_registration_token=False,
    )

    assert not new_user.last_registration_token

    username = random_email()
    new_user = user_service.create_new_user(
        username=username,
        email=username,
        password=random_password(),
        disabled=False,
        create_registration_token=True,
    )

    assert new_user.last_registration_token

    # check that user is set to expire when appropriate
    username = random_email()
    new_user = user_service.create_new_user(
        username=username,
        email=username,
        password=random_password(),
        disabled=False,
    )

    assert not new_user.user_expires

    username = random_email()
    new_user = user_service.create_new_user(
        username=username,
        email=username,
        password=random_password(),
        disabled=True,
    )

    assert new_user.user_expires


def test_update_user(user_service: UserService):
    username = random_email()
    new_user = user_service.create_new_user(
        username=username, email=username, password=random_password(), disabled=True
    )
    assert new_user.alexa_user_id is None
    assert new_user.todoist_user_id is None

    new_user.alexa_user_id = random_string()
    new_user.todoist_user_id = random_string()
    user_service.update_user(new_user)

    updated_user = user_service.get_user(username, active_only=False)
    assert updated_user
    assert updated_user.alexa_user_id and updated_user.alexa_user_id == new_user.alexa_user_id
    assert updated_user.todoist_user_id and updated_user.todoist_user_id == new_user.todoist_user_id

    # verify username and email are sanitized
    updated_user.username = username.upper() + " "
    updated_user.email = username.upper() + " "
    user_service.update_user(updated_user)

    updated_user = user_service.get_user(username, active_only=False)
    assert updated_user
    assert updated_user.username == username == username.lower()
    assert updated_user.email == username == username.lower()

    # cannot change a user's username
    username = random_email()
    user_service.create_new_user(username=username, email=username, password=random_password(), disabled=True)

    user = user_service.get_user(username, active_only=False)
    assert user
    assert not user.alexa_user_id

    user.alexa_user_id = random_string()
    updated_email = random_email()
    user.username = updated_email
    with pytest.raises(ValueError):
        user_service.update_user(user)

    # verify nothing changed
    assert not user_service.get_user(updated_email, active_only=False)
    user = user_service.get_user(username, active_only=False)
    assert user
    assert user.username == username
    assert not user.alexa_user_id

    # verify expiration is removed
    username = random_email()
    new_user = user_service.create_new_user(
        username=username, email=username, password=random_password(), disabled=True
    )
    assert new_user.user_expires

    user_service.update_user(new_user, remove_expiration=True)
    updated_user = user_service.get_user(username, active_only=False)
    assert updated_user
    assert not updated_user.user_expires


def test_update_atomic_user_field(user_service: UserService):
    username = random_email()
    new_user = user_service.create_new_user(
        username=username, email=username, password=random_password(), disabled=True
    )

    initial_value = random_int(0, 100)
    new_user.incorrect_login_attempts = initial_value
    user_service.update_user(new_user)

    increment = random_int(1, 100)
    response = user_service.update_atomic_user_field(
        new_user, field="incorrect_login_attempts", value=increment, operation=DynamoDBAtomicOp.increment
    )
    assert response == initial_value + increment


def test_change_user_password(user_service: UserService):
    username = random_email()
    initial_password = random_password()
    new_password = random_password()

    user_service.create_new_user(username=username, email=username, password=initial_password, disabled=False)
    user = user_service.get_authenticated_user(username, initial_password)
    assert user

    assert not user_service.get_authenticated_user(username, new_password)
    user_service.change_user_password(user, new_password)
    assert user_service.get_authenticated_user(username, new_password)
    assert not user_service.get_authenticated_user(username, initial_password)

    # enable a disabled user
    username = random_email()
    disabled_user = user_service.create_new_user(
        username=username, email=username, password=initial_password, disabled=True
    )
    assert disabled_user.disabled

    user_service.change_user_password(disabled_user, new_password, enable_user=True)
    assert not user_service.get_authenticated_user(username, initial_password)
    enabled_user = user_service.get_authenticated_user(username, new_password)
    assert enabled_user
    assert not enabled_user.disabled

    # clear reset token
    username = random_email()
    new_user = user_service.create_new_user(
        username=username, email=username, password=initial_password, disabled=False
    )
    new_user.last_password_reset_token = random_string()
    user_service.update_user(new_user)

    user = user_service.get_authenticated_user(username, initial_password)
    assert user
    assert user.last_password_reset_token

    user_service.change_user_password(user, new_password, clear_password_reset_token=False)
    user = user_service.get_authenticated_user(username, new_password)
    assert user
    assert user.last_password_reset_token

    user_service.change_user_password(user, initial_password, clear_password_reset_token=True)
    user = user_service.get_authenticated_user(username, initial_password)
    assert user
    assert not user.last_password_reset_token


def test_lockout_user_incorrect_login(user_service: UserService):
    username = random_email()
    password = random_password()
    user_service.create_new_user(username=username, email=username, password=password, disabled=False)

    config.LOGIN_LOCKOUT_ATTEMPTS = random_int(10, 20)
    for i in range(config.LOGIN_LOCKOUT_ATTEMPTS):
        with contextlib.suppress(UserIsDisabledError):
            assert not user_service.get_authenticated_user(username, random_password())

        # verify the user isn't locked out after three attempts
        # dynamodb atomic counters are not always accurate, especially in quick succession,
        # so we can't guarantee (config.LOGIN_LOCKOUT_ATTEMPTS - 1) attempts
        if i < 3:
            user = user_service.get_user(username)
            assert user
            assert not user.disabled
            assert user.incorrect_login_attempts

    # verify the user is locked out
    with pytest.raises(UserIsDisabledError):
        assert not user_service.get_authenticated_user(username, password)

    user = user_service.get_user(username, active_only=False)
    assert user
    assert user.disabled

    # verify the lockout counter is reset
    assert not user.incorrect_login_attempts


def test_update_rate_limit(user_service: UserService):
    username = random_email()
    password = random_password()
    new_user = user_service.create_new_user(username=username, email=username, password=password, disabled=False)

    # set initial rate limit
    expires = round(time.time()) + random_int(10_000, 100_000)
    new_user.rate_limit_map = {RateLimitCategory.read.value: UserRateLimit(value=0, expires=expires)}
    user_service.update_user(new_user)

    # increment it
    user_service.update_rate_limit(
        new_user, RateLimitCategory.read, DynamoDBAtomicOp.increment, value=random_int(1, 100)
    )
    user = user_service.get_user(username)
    assert user
    assert user.rate_limit_map

    rate_limit = user.rate_limit_map[RateLimitCategory.read.value]
    assert rate_limit
    new_rate_limit_value = rate_limit.value
    assert new_rate_limit_value > 0
    assert rate_limit.expires == expires

    # update expires
    new_expires = expires + random_int(10_000, 100_000)
    user_service.update_rate_limit(
        user, RateLimitCategory.read, DynamoDBAtomicOp.increment, value=random_int(1, 10), new_expires=new_expires
    )

    user = user_service.get_user(username)
    assert user
    assert user.rate_limit_map

    rate_limit = user.rate_limit_map[RateLimitCategory.read.value]
    assert rate_limit
    assert rate_limit.value > new_rate_limit_value
    assert rate_limit.expires == new_expires
