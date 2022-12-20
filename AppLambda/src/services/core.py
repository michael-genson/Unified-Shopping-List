from email.message import EmailMessage
from smtplib import SMTP
from typing import Optional

from passlib.context import CryptContext

from ..app_secrets import (
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_SENDER,
    SMTP_SERVER,
    SMTP_USERNAME,
    USERS_TABLENAME,
)
from ..clients.aws import DynamoDB
from ..config import ACCESS_TOKEN_EXPIRE_MINUTES_REGISTRATION
from ..models.core import User, UserInDB

users_db = DynamoDB(USERS_TABLENAME)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserAlreadyExistsError(Exception):
    def __init__(self):
        super().__init__("User already exists")


class CoreUserService:
    def __init__(self) -> None:
        self.db_primary_key = "username"
        self.db = users_db

    def get_user(self, username: str, active_only=True) -> Optional[UserInDB]:
        """Fetches a user from the database without authentication, if it exists"""

        user_data = self.db.get(self.db_primary_key, username.strip().lower())
        if not user_data:
            return None

        user = UserInDB.parse_obj(user_data)
        if active_only and user.disabled:
            return None

        return user

    def delete_user(self, username: str) -> None:
        """Removes the user and all user data"""

        self.db.delete(self.db_primary_key, username)
        return None

    def get_usernames_by_secondary_index(self, gsi_key: str, gsi_value: str) -> list[str]:
        """Queries database using a global secondary index and returns all usernames with that value"""

        user_data = self.db.query(gsi_key, gsi_value)
        return [str(data.get(self.db_primary_key)) for data in user_data]

    def authenticate_user(self, user: UserInDB, password: str) -> Optional[User]:
        """Validates if a user is successfully authenticated"""

        # verify the provided password is correct
        if not pwd_context.verify(password, user.hashed_password):
            return None

        return user.cast(User)

    def get_authenticated_user(self, username: str, password: str) -> Optional[User]:
        """Fetches a user from the database only if authenticated, if it exists"""

        user = self.get_user(username)
        if not user:
            return None

        return self.authenticate_user(user, password)

    def create_new_user(
        self, username: str, email: str, password: str, disabled: bool = False
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
            new_user.set_expiration(ACCESS_TOKEN_EXPIRE_MINUTES_REGISTRATION * 60)

        self.db.put(new_user.dict(exclude_none=True), allow_update=allow_update)
        return new_user

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


class SMTPService:
    def __init__(
        self,
        server: str = SMTP_SERVER,
        port: int = SMTP_PORT,
        username: str = SMTP_USERNAME,
        password: str = SMTP_PASSWORD,
        use_tls: bool = True,
    ) -> None:
        self.server = server
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls

    def send(self, msg: EmailMessage) -> None:
        smtp = SMTP(self.server, port=self.port)

        smtp.ehlo()
        smtp.starttls()

        smtp.login(self.username, self.password)
        smtp.send_message(msg)
