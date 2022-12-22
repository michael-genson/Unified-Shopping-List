import logging
from datetime import timedelta
from typing import Any, Optional, Union, cast

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, Path, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from requests import PreparedRequest

from ..app import app, smtp_service, templates, token_service, users_service
from ..app_secrets import EMAIL_WHITELIST, USE_REGISTRATION_WHITELIST
from ..config import ACCESS_TOKEN_EXPIRE_MINUTES_REGISTRATION
from ..models.core import Token, User
from ..models.email import RegistrationEmail
from ..services.auth import InvalidTokenError
from ..services.core import UserAlreadyExistsError

frontend_router = APIRouter(prefix="/app", tags=["Application"])


class WhitelistError(Exception):
    def __init__(self):
        super().__init__("You are not whitelisted on this application")


async def get_user_session(request: Request, response: Response) -> Optional[User]:
    """Authenticate the user using their access token cookie"""

    access_token = request.cookies.get("access_token")
    if not access_token:
        return None

    try:
        username = token_service.get_username_from_token(access_token)

    except InvalidTokenError:
        return None

    _user_in_db = users_service.get_user(username)
    if not _user_in_db:
        return None

    return _user_in_db.cast(User)


async def redirect_if_not_logged_in(
    request: Request, redirect_path: Optional[str] = None, params: Optional[dict] = None
) -> Union[Response, User]:
    """Return a user if logged in, or a redirect response"""

    if params is None:
        params = {}

    response = RedirectResponse(frontend_router.url_path_for("log_in"), status_code=302)
    user = await get_user_session(request, response)

    if user:
        return user

    if redirect_path:
        route_url = str(request.base_url)[:-1] + redirect_path
        req = PreparedRequest()
        req.prepare_url(route_url, params)
        redirect_url = cast(str, req.url)

        response.set_cookie(key="redirect", value=redirect_url, httponly=True)

    return response


async def set_user_session(response: Response, token: Token) -> None:
    """Add the access token cookie"""

    response.set_cookie(key="access_token", value=token.access_token, httponly=True)


async def clear_user_session(response: Response) -> None:
    """Remove the access token cookie"""

    response.delete_cookie(key="access_token")


@frontend_router.get("", response_class=HTMLResponse)
async def home(request: Request, response: Response):
    """Render the home page"""

    if app.docs_url:
        docs_url = str(request.base_url)[:-1] + app.docs_url

    user = await get_user_session(request, response)
    return templates.TemplateResponse(
        "home.html", {"request": request, "user": user, "docs_url": docs_url}
    )


@frontend_router.get("/privacy-policy", response_class=HTMLResponse)
async def privacy_policy(request: Request, response: Response):
    user = await get_user_session(request, response)
    return templates.TemplateResponse(
        "privacy_policy.html", context={"request": request, "user": user}
    )


@frontend_router.get("/login", response_class=HTMLResponse)
async def log_in(request: Request, error=False, redirect=None):
    """Render the login page"""

    redirect = request.cookies.get("redirect")
    response = RedirectResponse(redirect or frontend_router.url_path_for("home"), status_code=302)
    response.delete_cookie(key="redirect")

    if await get_user_session(request, response):
        return response

    return templates.TemplateResponse("login.html", {"request": request, "login_error": error})


@frontend_router.post("/login", response_class=HTMLResponse)
async def log_in_user(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """Log the user in and store the access token in the user's cookies"""

    try:
        user = users_service.get_authenticated_user(form_data.username, form_data.password)
        if not user:
            return Exception("Invalid login")

    except Exception:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "login_error": True, "username": form_data.username},
        )

    token = token_service.create_token(user.username)
    redirect = request.cookies.get("redirect")
    response = RedirectResponse(redirect or frontend_router.url_path_for("home"), status_code=302)

    await set_user_session(response, token)
    return response


@frontend_router.get("/register", response_class=HTMLResponse)
async def register(request: Request, token_expired: bool = False):
    """Render the registration page"""

    response = RedirectResponse(frontend_router.url_path_for("home"), status_code=302)
    if await get_user_session(request, response):
        return response

    context: dict[str, Any] = {"request": request}
    if token_expired:
        context["registration_error"] = "Unable to complete registration. Token has expired"

    return templates.TemplateResponse("register.html", context)


@frontend_router.post("/register", response_class=HTMLResponse)
async def send_user_registration(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """Register the user and return them to the home page"""

    # verify password length
    if len(form_data.password) < 8:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "registration_error": "Password must be at least 8 characters long",
                "username": form_data.username,
            },
        )

    # create disabled user and generate a temporary registration token for them
    try:
        clean_email = form_data.username.strip().lower()
        if USE_REGISTRATION_WHITELIST and clean_email not in EMAIL_WHITELIST:
            raise WhitelistError()

        new_user = users_service.create_new_user(
            username=clean_email, email=clean_email, password=form_data.password, disabled=True
        )

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES_REGISTRATION)
        registration_token = token_service.create_token(new_user.username, access_token_expires)

    except (ClientError, UserAlreadyExistsError) as e:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "registration_error": "Username already taken!",
                "username": form_data.username,
            },
        )

    except WhitelistError:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "registration_error": "You are not whitelisted on this app",
                "username": form_data.username,
            },
        )

    except Exception as e:
        logging.error(
            f"Unhandled exception when trying to register a new user ({form_data.username})"
        )
        logging.error(f"{type(e).__name__}: {e}")

        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "registration_error": "An unknown error occurred during registration",
                "username": form_data.username,
            },
        )

    try:
        # send registration email
        msg = RegistrationEmail()
        full_registration_url = str(request.base_url)[:-1] + frontend_router.url_path_for(
            "complete_registration", registration_token=registration_token.access_token
        )

        smtp_service.send(
            msg.message(
                form_data.username,
                form_data.username,
                registration_url=full_registration_url,
            )
        )

        return templates.TemplateResponse(
            "register.html",
            {"request": request, "registration_email_sent": True},
        )

    except Exception as e:
        logging.error(
            f"Unhandled exception when trying to send a new user ({form_data.username}) their registration email"
        )
        logging.error(f"{type(e).__name__}: {e}")

        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "registration_error": "An unknown error occurred during registration",
                "username": form_data.username,
            },
        )


@frontend_router.get("/complete_registration/{registration_token}", response_class=HTMLResponse)
async def complete_registration(request: Request, registration_token: str = Path(...)):
    """Enables a user and logs them in"""

    try:
        username = token_service.get_username_from_token(registration_token)
        _user_in_db = users_service.get_user(username, active_only=False)
        if not _user_in_db:
            raise InvalidTokenError()

    except InvalidTokenError:
        return RedirectResponse(
            frontend_router.url_path_for("register") + "?token_expired=true", status_code=302
        )

    user = _user_in_db.cast(User)
    user.disabled = False
    users_service.update_user(user, remove_expiration=True)
    token = token_service.refresh_token(registration_token)

    response = RedirectResponse(frontend_router.url_path_for("home"), status_code=302)
    await set_user_session(response, token)
    return response


@frontend_router.post("/logout", response_class=HTMLResponse)
async def log_out_user(response: Response):
    """Log the user out and return to the home page"""

    response = RedirectResponse(frontend_router.url_path_for("home"), status_code=302)
    await clear_user_session(response)
    return response


@frontend_router.post("/delete-account", response_class=HTMLResponse)
async def delete_user(request: Request, response: Response):
    """Completely remove all user data"""

    response = RedirectResponse(frontend_router.url_path_for("home"), status_code=302)
    user = await get_user_session(request, response)
    if not user:
        return response

    users_service.delete_user(user.username)
    await clear_user_session(response)
    return response
