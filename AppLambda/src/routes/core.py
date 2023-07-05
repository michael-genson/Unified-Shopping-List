import logging
from datetime import timedelta
from typing import Any, cast

from botocore.exceptions import ClientError
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from requests import PreparedRequest

from ..app import app, secrets, services, settings, templates
from ..models.core import Token, User, WhitelistError
from ..models.email import PasswordResetEmail, RegistrationEmail
from ..services.auth_token import InvalidTokenError
from ..services.user import UserAlreadyExistsError, UserIsDisabledError, UserIsNotRegisteredError

router = APIRouter(prefix="/app", tags=["Application"])


async def get_user_session(request: Request) -> User | None:
    """Authenticate the user using their access token cookie"""

    access_token = request.cookies.get("access_token")
    if not access_token:
        return None

    try:
        username = services.token.get_username_from_token(access_token)

    except InvalidTokenError:
        return None

    _user_in_db = services.user.get_user(username)
    if not _user_in_db:
        return None

    return _user_in_db.cast(User)


async def redirect_if_not_logged_in(
    request: Request, redirect_path: str | None = None, params: dict | None = None
) -> Response | User:
    """Return a user if logged in, or a redirect response"""

    if params is None:
        params = {}

    response = RedirectResponse(router.url_path_for("log_in"), status_code=302)
    user = await get_user_session(request)

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


def send_registration_email(registration_url: str, username: str, email: str):
    try:
        msg = RegistrationEmail()
        services.smtp.send(msg.message(username, email, registration_url=registration_url))

    except Exception as e:
        logging.error(f"Unhandled exception when trying to send a new user ({username}) their registration email")
        logging.error(f"{type(e).__name__}: {e}")


def send_password_reset_email(password_reset_url: str, username: str, email: str):
    try:
        msg = PasswordResetEmail()
        services.smtp.send(msg.message(username, email, password_reset_url=password_reset_url))

    except Exception as e:
        logging.error(f"Unhandled exception when trying to send a user ({username}) their password reset email")
        logging.error(f"{type(e).__name__}: {e}")


@router.get("", response_class=HTMLResponse)
async def home(request: Request, response: Response):
    """Render the home page"""

    if app.docs_url:
        docs_url = str(request.base_url)[:-1] + app.docs_url

    user = await get_user_session(request)
    return templates.TemplateResponse("home.html", {"request": request, "user": user, "docs_url": docs_url})


@router.get("/privacy-policy", response_class=HTMLResponse)
async def privacy_policy(request: Request, response: Response):
    user = await get_user_session(request)
    return templates.TemplateResponse("privacy_policy.html", context={"request": request, "user": user})


@router.get("/login", response_class=HTMLResponse)
async def log_in(request: Request, error=False, redirect=None, reset_password=False):
    """Render the login page"""

    redirect = request.cookies.get("redirect")
    response = RedirectResponse(redirect or router.url_path_for("home"), status_code=302)
    response.delete_cookie(key="redirect")

    if await get_user_session(request):
        return response

    login_error = "Invalid login" if error else None

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "login_error": login_error, "reset_password": reset_password},
    )


@router.post("/login", response_class=HTMLResponse)
async def log_in_user(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """Log the user in and store the access token in the user's cookies"""

    try:
        user = services.user.get_authenticated_user(form_data.username, form_data.password)
        if not user:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "login_error": "Invalid login",
                    "username": form_data.username,
                },
            )

    except UserIsNotRegisteredError:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "login_error": "You must complete registration before logging in. Check your email, or re-register",
                "username": form_data.username,
            },
        )

    except UserIsDisabledError:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "login_error": "You have been locked out. Please reset your password",
                "username": form_data.username,
            },
        )

    except WhitelistError:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "login_error": "You are not whitelisted on this server",
                "username": form_data.username,
            },
        )

    token = services.token.create_token(user.username)
    redirect = request.cookies.get("redirect")
    response = RedirectResponse(redirect or router.url_path_for("home"), status_code=302)

    await set_user_session(response, token)
    return response


@router.get("/login/forgot-password", response_class=HTMLResponse)
async def forgot_password(request: Request, token_expired: bool = False):
    """Renders the forgot password page"""

    if await get_user_session(request):
        return RedirectResponse(router.url_path_for("home"), status_code=302)

    context: dict[str, Any] = {"request": request}
    if token_expired:
        context["password_reset_error"] = "Unable to reset password. Token has expired. Please try again"

    return templates.TemplateResponse("password_reset.html", context)


@router.post("/login/forgot-password", response_class=HTMLResponse)
async def initiate_password_reset_email(
    request: Request,
    background_tasks: BackgroundTasks,
    username=Form(),
):
    """Sends a password reset email to the user"""

    # if there is no user, we pretend we sent the email anyway
    _user_in_db = services.user.get_user(username, active_only=False)
    if _user_in_db:
        user = _user_in_db.cast(User)

        expires = timedelta(minutes=settings.access_token_expire_minutes_reset_password)
        reset_token = services.token.create_token(user.username, expires)

        user.last_password_reset_token = reset_token.access_token
        services.user.update_user(user)

        password_reset_url = (
            str(request.base_url)[:-1]
            + router.url_path_for("reset_password")
            + f"?reset_token={user.last_password_reset_token}"
        )

        background_tasks.add_task(
            send_password_reset_email,
            password_reset_url=password_reset_url,
            username=user.username,
            email=user.email,
        )

    return templates.TemplateResponse(
        "password_reset.html",
        {"request": request, "password_reset": True},
    )


@router.get("/login/reset-password", response_class=HTMLResponse)
async def reset_password(request: Request, reset_token: str | None = None):
    """Renders the password reset form, if the user is authenticated"""

    try:
        if not reset_token:
            raise InvalidTokenError()

        username = services.token.get_username_from_token(reset_token)
        _user_in_db = services.user.get_user(username, active_only=False)

        if not _user_in_db or _user_in_db.last_password_reset_token != reset_token:
            raise InvalidTokenError()

    except InvalidTokenError:
        return RedirectResponse(
            router.url_path_for("forgot_password") + "?token_expired=true",
            status_code=302,
        )

    return templates.TemplateResponse("change_password.html", {"request": request})


@router.post("/login/reset-password", response_class=HTMLResponse)
async def update_password(request: Request, reset_token: str | None = None, password: str = Form()):
    """Updates the user's password"""
    if len(password) < 8:
        return templates.TemplateResponse("change_password.html", {"request": request})

    try:
        if not reset_token:
            raise InvalidTokenError()

        username = services.token.get_username_from_token(reset_token)
        _user_in_db = services.user.get_user(username, active_only=False)

        if not _user_in_db or _user_in_db.last_password_reset_token != reset_token:
            raise InvalidTokenError()

        user = _user_in_db.cast(User)

    except InvalidTokenError:
        return RedirectResponse(
            router.url_path_for("forgot_password") + "?token_expired=true",
            status_code=302,
        )

    services.user.change_user_password(user, password)
    return RedirectResponse(router.url_path_for("log_in") + "?reset_password=true", status_code=302)


@router.get("/register", response_class=HTMLResponse)
async def register(request: Request, token_expired: bool = False):
    """Render the registration page"""

    response = RedirectResponse(router.url_path_for("home"), status_code=302)
    if await get_user_session(request):
        return response

    context: dict[str, Any] = {"request": request}
    if token_expired:
        context["registration_error"] = "Unable to complete registration. Token has expired"

    return templates.TemplateResponse("register.html", context)


@router.post("/register", response_class=HTMLResponse)
async def initiate_registration_email(
    request: Request,
    background_tasks: BackgroundTasks,
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
        if settings.use_whitelist and clean_email not in secrets.email_whitelist:
            raise WhitelistError()

        new_user = services.user.create_new_user(
            username=clean_email,
            email=clean_email,
            password=form_data.password,
            disabled=True,
        )

    except (ClientError, UserAlreadyExistsError):
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
        logging.error(f"Unhandled exception when trying to register a new user ({form_data.username})")
        logging.error(f"{type(e).__name__}: {e}")

        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "registration_error": "An unknown error occurred during registration",
                "username": form_data.username,
            },
        )

    registration_url = (
        str(request.base_url)[:-1]
        + router.url_path_for("complete_registration")
        + f"?registration_token={new_user.last_registration_token}"
    )

    background_tasks.add_task(
        send_registration_email,
        registration_url=registration_url,
        username=form_data.username,
        email=form_data.username,
    )

    return templates.TemplateResponse(
        "register.html",
        {"request": request, "registration_email_sent": True},
    )


@router.get("/complete_registration", response_class=HTMLResponse)
async def complete_registration(registration_token: str | None = None):
    """Enables a user and logs them in"""

    try:
        if not registration_token:
            raise InvalidTokenError()

        username = services.token.get_username_from_token(registration_token)
        _user_in_db = services.user.get_user(username, active_only=False)
        if not _user_in_db or _user_in_db.last_registration_token != registration_token:
            raise InvalidTokenError()

    except InvalidTokenError:
        return RedirectResponse(router.url_path_for("register") + "?token_expired=true", status_code=302)

    user = _user_in_db.cast(User)
    user.disabled = False
    user.last_registration_token = None
    services.user.update_user(user, remove_expiration=True)
    token = services.token.refresh_token(registration_token)

    response = RedirectResponse(router.url_path_for("home"), status_code=302)
    await set_user_session(response, token)
    return response


@router.post("/logout", response_class=HTMLResponse)
async def log_out_user(response: Response):
    """Log the user out and return to the home page"""

    response = RedirectResponse(router.url_path_for("home"), status_code=302)
    await clear_user_session(response)
    return response


@router.post("/delete-account", response_class=HTMLResponse)
async def delete_user(request: Request, response: Response):
    """Completely remove all user data"""

    response = RedirectResponse(router.url_path_for("home"), status_code=302)
    user = await get_user_session(request)
    if not user:
        return response

    services.user.delete_user(user.username)
    await clear_user_session(response)
    return response
