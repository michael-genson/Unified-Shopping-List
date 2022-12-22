from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from ..app import token_service, users_service
from ..app_secrets import EMAIL_WHITELIST, USE_REGISTRATION_WHITELIST
from ..config import ACCESS_TOKEN_EXPIRE_MINUTES_REGISTRATION
from ..models.core import Token, User
from ..services.auth import InvalidTokenError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/authorization/token")


router = APIRouter(prefix="/api/authorization", tags=["Authorization"])


class WhitelistError(Exception):
    def __init__(self):
        super().__init__("You are not whitelisted on this application")


def create_new_user(form_data: OAuth2PasswordRequestForm) -> Token:
    """Creates a disabled user and returns a registration token"""

    clean_email = form_data.username.strip().lower()
    if USE_REGISTRATION_WHITELIST and clean_email not in EMAIL_WHITELIST:
        raise WhitelistError()

    new_user = users_service.create_new_user(
        username=clean_email, email=clean_email, password=form_data.password, disabled=True
    )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES_REGISTRATION)
    return token_service.create_token(new_user.username, access_token_expires)


async def enable_user_from_token(token: str) -> User:
    user = await get_current_user(token)
    user.disabled = False
    users_service.update_user(user, remove_expiration=True)
    return user


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Gets the currently authenticated user. Does not check whether the user is active (see `get_current_active_user`)"""

    try:
        username = token_service.get_username_from_token(token)
        _user_in_db = users_service.get_user(username, active_only=False)
        if _user_in_db is None:
            raise InvalidTokenError()

    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _user_in_db.cast(User)


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Gets the currently authenticated user and verifies that they're active"""

    if current_user.disabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

    return current_user


async def delete_existing_user(user: User = Depends(get_current_active_user)) -> None:
    """Deletes the user and all of their data"""

    users_service.delete_user(user.username)
    return None


@router.post("/token", response_model=Token)
async def log_in_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> Token:
    """Generates a new token from a username and password"""

    user = users_service.get_authenticated_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token_service.create_token(user.username)


@router.get("/me", response_model=User)
async def get_logged_in_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    return current_user
