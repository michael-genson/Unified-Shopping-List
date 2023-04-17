from datetime import timedelta
from typing import Optional

from passlib.context import CryptContext

from .. import config
from ..app_secrets import EMAIL_WHITELIST
from ..clients import aws
from ..models.aws import DynamoDBAtomicOp
from ..models.core import RateLimitCategory, User, UserInDB, WhitelistError
from .auth_token import AuthTokenService

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserAlreadyExistsError(Exception):
    def __init__(self):
        super().__init__("User already exists")


class UserIsNotRegisteredError(Exception):
    def __init__(self):
        super().__init__("User has not completed registration")


class UserIsDisabledError(Exception):
    def __init__(self):
        super().__init__("User is disabled")


class UserService:
    def __init__(self, token_service: AuthTokenService) -> None:
        self._token_service = token_service
        self._db: Optional[aws.DynamoDB] = None

    @property
    def db(self):
        if not self._db:
            self._db = aws.DynamoDB(config.USERS_TABLENAME, config.USERS_PK)

        return self._db

    def get_user(self, username: str, active_only=True) -> Optional[UserInDB]:
        """Fetches a user from the database without authentication, if it exists"""

        user_data = self.db.get(username.strip().lower())
        if not user_data:
            return None

        user = UserInDB.parse_obj(user_data)
        if active_only and user.disabled:
            return None

        return user

    def delete_user(self, username: str) -> None:
        """Removes the user and all user data"""

        self.db.delete(username)
        return None

    def get_usernames_by_secondary_index(self, gsi_key: str, gsi_value: str) -> list[str]:
        """Queries database using a global secondary index and returns all usernames with that value"""

        user_data = self.db.query(gsi_key, gsi_value)
        return [str(data.get(config.USERS_PK)) for data in user_data]

    def authenticate_user(self, user: UserInDB, password: str) -> Optional[User]:
        """Validates if a user is successfully authenticated"""

        # verify the provided password is correct
        if not pwd_context.verify(password, user.hashed_password):
            self.increment_failed_login_counter(user)
            return None

        if user.incorrect_login_attempts and user.incorrect_login_attempts > 0:
            user.incorrect_login_attempts = 0
            self.update_user(user)

        return user.cast(User)

    def get_authenticated_user(self, username: str, password: str) -> Optional[User]:
        """
        Fetches a user from the database only if authenticated, if it exists

        If the user is new and must register, raises UserIsNotRegisteredError
        If the user has been locked out, raises UserIsDisabledError
        """

        user = self.get_user(username, active_only=False)
        if not user:
            return None

        if user.disabled:
            if user.user_expires:
                raise UserIsNotRegisteredError()

            else:
                raise UserIsDisabledError()

        if config.USE_WHITELIST and user.email not in EMAIL_WHITELIST:
            raise WhitelistError()

        return self.authenticate_user(user, password)

    def create_new_user(
        self,
        username: str,
        email: str,
        password: str,
        disabled: bool = False,
        create_registration_token: bool = True,
    ) -> User:
        """Creates a new user if the username isn't in use"""

        allow_update = False
        existing_user = self.get_user(username, active_only=False)
        if existing_user:
            if not existing_user.disabled:
                raise UserAlreadyExistsError()

            # if the user exists but is disabled, replace them with the new user
            else:
                allow_update = True

        new_user = UserInDB(
            username=username.strip().lower(),
            email=email.strip().lower(),
            hashed_password=pwd_context.hash(password),
            disabled=disabled,
        )

        if disabled:
            new_user.set_expiration(config.ACCESS_TOKEN_EXPIRE_MINUTES_REGISTRATION * 60)

        if create_registration_token:
            access_token_expires = timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES_REGISTRATION)
            registration_token = self._token_service.create_token(new_user.username, access_token_expires)

            new_user.last_registration_token = registration_token.access_token

        self.db.put(new_user.dict(exclude_none=True), allow_update=allow_update)
        return new_user.cast(User)

    def update_user(self, user: User, remove_expiration: bool = False) -> None:
        """Updates an existing user"""

        user_to_update = self.get_user(user.username, active_only=False)
        if not user_to_update:
            raise ValueError(f"User {user.username} does not exist")

        user_to_update.merge(user)
        user_to_update.username = user_to_update.username.strip().lower()
        user_to_update.email = user_to_update.email.strip().lower()

        data = user_to_update.dict(exclude_none=True)
        if remove_expiration:
            data["user_expires"] = None

        self.db.put(data)

    def update_atomic_user_field(
        self,
        user: User,
        field: str,
        value: int = 1,
        operation: DynamoDBAtomicOp = DynamoDBAtomicOp.increment,
    ) -> int:
        """
        Increments or decrements a field by a given amount and returns the new value.
        Should not be used if precision is critical

        For nested fields, use dot notation for the field name (e.g. "stats.counters.likes")
        Raises <botocore.exceptions.ClientError> if the field doesn't exist or the field value isn't an int
        """

        return self.db.atomic_op(
            primary_key_value=user.username.strip().lower(),
            attribute=field,
            attribute_change_value=value,
            op=operation,
        )

    def change_user_password(
        self,
        user: User,
        new_password: str,
        enable_user: bool = True,
        clear_password_reset_token: bool = True,
    ) -> None:
        """Changes a user's password"""

        user_to_update = self.get_user(user.username, active_only=False)
        if not user_to_update:
            raise ValueError(f"User {user.username} does not exist")

        user_to_update.hashed_password = pwd_context.hash(new_password)
        if enable_user:
            user_to_update.disabled = False

        data = user_to_update.dict(exclude_none=True)
        if clear_password_reset_token:
            data["last_password_reset_token"] = None

        self.db.put(data)

    def increment_failed_login_counter(self, user: User) -> User:
        """
        Increments the user's failed login counter and returns the updated user

        If the user fails to login too many times, they will be locked out
        """

        if user.incorrect_login_attempts is None:
            user.incorrect_login_attempts = 1
            self.update_user(user)
            return user

        user.incorrect_login_attempts += 1
        if user.incorrect_login_attempts < config.LOGIN_LOCKOUT_ATTEMPTS:
            user.incorrect_login_attempts = self.update_atomic_user_field(user, "incorrect_login_attempts")

            return user

        # if the user has been locked out, disable them
        user.disabled = True
        user.incorrect_login_attempts = 0

        self.update_user(user)
        return user

    def update_rate_limit(
        self,
        user: User,
        category: RateLimitCategory,
        operation: DynamoDBAtomicOp,
        value: int = 1,
        new_expires: Optional[int] = None,
    ) -> None:
        """
        Updates a user's rate limit and returns the updates user. Optionally provide a new expires value

        Raises <botocore.exceptions.ClientError> if the user doesn't already have a rate limit set for this category
        """

        field_root = f"rate_limit_map.{category.value}"
        self.update_atomic_user_field(user=user, field=f"{field_root}.value", value=value, operation=operation)

        if new_expires:
            self.update_atomic_user_field(
                user=user,
                field=f"{field_root}.expires",
                value=new_expires,
                operation=DynamoDBAtomicOp.overwrite,
            )
