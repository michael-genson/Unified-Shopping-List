from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from ..app import services
from ..models.core import RateLimitCategory, Token, User, WhitelistError
from ..services.auth_token import InvalidTokenError
from ..services.user import UserIsDisabledError, UserIsNotRegisteredError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/authorization/token")
router = APIRouter(prefix="/api/authorization", tags=["Authorization"])


# TODO: move this to a service
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Gets the currently authenticated user and verifies that they're active"""

    try:
        username = services.token.get_username_from_token(token)
        _user_in_db = services.user.get_user(username, active_only=False)
        if _user_in_db is None:
            raise InvalidTokenError()

    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = _user_in_db.cast(User)

    if user.disabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

    return user


@router.post("/token", response_model=Token)
async def log_in_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> Token:
    """Generates a new token from a username and password"""

    try:
        user = services.user.get_authenticated_user(form_data.username, form_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return services.token.create_token(user.username)

    except UserIsNotRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User has not completed registration",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except UserIsDisabledError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is disabled and must request a password reset",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except WhitelistError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is not whitelisted on this server",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/me", response_model=User)
@services.rate_limit.limit(RateLimitCategory.read)
async def get_logged_in_user(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user
