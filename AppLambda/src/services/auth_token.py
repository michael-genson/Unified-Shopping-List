from datetime import datetime, timedelta

from jose import JWTError, jwt

from ..app import secrets, settings
from ..models.core import Token


class InvalidTokenError(Exception):
    def __init__(self):
        super().__init__("Invalid token")


class AuthTokenService:
    def create_token(self, username: str, expires: timedelta | None = None) -> Token:
        """Creates a new access token for a user"""

        if not expires:
            expires = timedelta(minutes=settings.access_token_expire_minutes)

        expiration = datetime.utcnow() + expires

        data = {"sub": username, "exp": expiration}
        access_token = jwt.encode(data, secrets.db_secret_key, algorithm=secrets.db_algorithm)
        return Token(access_token=access_token, token_type="Bearer")

    def get_username_from_token(self, access_token: str) -> str:
        """
        Decodes a token and returns the username.

        Raises a InvalidTokenError if the token is invalid or expired.
        """

        try:
            payload = jwt.decode(access_token, secrets.db_secret_key, algorithms=[secrets.db_algorithm])
            username: str | None = payload.get("sub")

        except JWTError:
            raise InvalidTokenError()

        if not username:
            raise InvalidTokenError()

        return username

    def refresh_token(self, access_token: str, expires: timedelta | None = None) -> Token:
        """Takes a valid access token and returns a new one"""

        username = self.get_username_from_token(access_token)
        return self.create_token(username, expires)
