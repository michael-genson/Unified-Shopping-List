from typing import Optional, Union, cast

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from requests import PreparedRequest

from ..app import app, templates
from ..models.core import Token, User
from ..routes.auth import (
    WhitelistError,
    create_new_user,
    delete_existing_user,
    get_current_active_user,
    get_current_user,
    log_in_for_access_token,
)

frontend_router = APIRouter(prefix="/app", tags=["Application"])


async def get_user_session(request: Request, response: Response) -> Optional[User]:
    """Authenticate the user using their access token cookie"""

    access_token = request.cookies.get("access_token")
    if not access_token:
        return None

    try:
        user = await get_current_user(access_token)
        return await get_current_active_user(user)

    except HTTPException:
        await clear_user_session(response)
        return None


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
        token = await log_in_for_access_token(form_data)

    except HTTPException:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "login_error": True, "username": form_data.username},
        )

    redirect = request.cookies.get("redirect")
    response = RedirectResponse(redirect or frontend_router.url_path_for("home"), status_code=302)
    await set_user_session(response, token)
    return response


@frontend_router.get("/register", response_class=HTMLResponse)
async def register(request: Request):
    """Render the registration page"""

    response = RedirectResponse(frontend_router.url_path_for("home"), status_code=302)
    if await get_user_session(request, response):
        return response

    return templates.TemplateResponse("register.html", {"request": request})


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

    # TODO: send verification email instead of directly creating the user
    try:
        create_new_user(form_data)

    except ValueError as e:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "registration_error": str(e),
                "username": form_data.username,
            },
        )

    except ClientError as e:
        print(e)
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

    except Exception:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "registration_error": "An unknown error occurred during registration",
                "username": form_data.username,
            },
        )

    token = await log_in_for_access_token(form_data)
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

    await delete_existing_user(user)
    await clear_user_session(response)
    return response
