from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt

from ..app_secrets import ALGORITHM, SECRET_KEY
from ..config import ACCESS_TOKEN_EXPIRE_MINUTES
from ..models.core import Token


class InvalidTokenError(Exception):
    def __init__(self):
        super().__init__("Invalid token")


class AuthTokenService:
    def __init__(self) -> None:
        pass

    def create_token(self, username: str, expires: Optional[timedelta] = None) -> Token:
        """Creates a new access token for a user"""

        if not expires:
            expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

        expiration = datetime.utcnow() + expires

        data = {"sub": username, "exp": expiration}
        access_token = jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)
        return Token(access_token=access_token, token_type="Bearer")

    def get_username_from_token(self, access_token: str) -> str:
        """
        Decodes a token and returns the username.

        Raises a InvalidTokenError if the token is invalid or expired.
        """

        try:
            payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
            username: Optional[str] = payload.get("sub")

        except JWTError:
            raise InvalidTokenError()

        if not username:
            raise InvalidTokenError()

        return username

    def refresh_token(self, access_token: str, expires: Optional[timedelta] = None) -> Token:
        """Takes a valid access token and returns a new one"""

        username = self.get_username_from_token(access_token)
        return self.create_token(username, expires)
