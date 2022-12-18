from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt

from ..app_secrets import (
    ALGORITHM,
    EMAIL_WHITELIST,
    SECRET_KEY,
    USE_REGISTRATION_WHITELIST,
)
from ..config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ACCESS_TOKEN_EXPIRE_MINUTES_REGISTRATION,
)
from ..models.core import Token, User
from ..services.core import CoreUserService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/authorization/token")
users_db = CoreUserService()

router = APIRouter(prefix="/api/authorization", tags=["Authorization"])


class WhitelistError(Exception):
    def __init__(self):
        super().__init__("You are not whitelisted on this application")


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    if not expires_delta:
        expires_delta = timedelta(minutes=15)

    expiration = datetime.utcnow() + expires_delta
    to_encode = data.copy()
    to_encode["exp"] = expiration

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def refresh_access_token(access_token: str, expiration_minutes=None) -> str:
    """Creates a new access token from an existing access token or auth code"""

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    access_token_expires = timedelta(minutes=expiration_minutes or ACCESS_TOKEN_EXPIRE_MINUTES)
    return create_access_token(data={"sub": username}, expires_delta=access_token_expires)


def create_new_user(form_data: OAuth2PasswordRequestForm) -> str:
    """Creates a disabled user and returns a JWT to enable them"""

    clean_email = form_data.username.strip().lower()
    if USE_REGISTRATION_WHITELIST and clean_email not in EMAIL_WHITELIST:
        raise WhitelistError()

    new_user = users_db.create_new_user(
        username=clean_email, email=clean_email, password=form_data.password, disabled=True
    )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES_REGISTRATION)
    return create_access_token(data={"sub": new_user.username}, expires_delta=access_token_expires)


async def enable_user_from_token(token: str) -> User:
    user = await get_current_user(token)
    user.disabled = False
    users_db.update_user(user, remove_expiration=True)
    return user


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Gets the currently authenticated user. Does not check whether the user is active (see `get_current_active_user`)"""

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    user = users_db.get_user(username, active_only=False)
    if user is None:
        raise credentials_exception

    return user.cast(User)


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Gets the currently authenticated user and verifies that they're active"""

    if current_user.disabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    return current_user


async def delete_existing_user(user: User = Depends(get_current_active_user)) -> None:
    """Deletes the user and all of their data"""

    users_db.delete_user(user.username)
    return None


@router.post("/token", response_model=Token)
async def log_in_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> Token:
    """Generates a new token from a username and password"""

    user = users_db.get_authenticated_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=User)
async def get_logged_in_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    return current_user
