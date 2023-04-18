from json import JSONDecodeError
from typing import cast
from uuid import uuid4

import requests
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from requests import HTTPError, PreparedRequest

from ..app import secrets, settings, templates
from ..models.account_linking import UserTodoistConfigurationCreate, UserTodoistConfigurationUpdate
from ..models.core import User
from ..models.todoist import TodoistAuthRequest, TodoistRedirect, TodoistTokenExchangeRequest, TodoistTokenResponse
from .account_linking import link_todoist_account, unlink_todoist_account, update_todoist_account_link
from .core import redirect_if_not_logged_in

auth_router = APIRouter(prefix="/authorization/todoist", tags=["Todoist"])
frontend_router = APIRouter(prefix="/app/todoist", tags=["Todoist"])

TODOIST_STATE_COOKIE = "todoist_state"

### Frontend ###


def create_todoist_config_template(request: Request, user: User, **kwargs):
    context = {
        "request": request,
        "user": user,
    }

    response = templates.TemplateResponse(
        "todoist_config.html",
        {**context, **{k: v for k, v in kwargs.items() if k not in context}},
    )

    response.delete_cookie(key="todoist_state")
    return response


@frontend_router.get("", response_class=HTMLResponse)
async def configure_todoist(request: Request):
    """Render the Todoist authorization page"""

    logged_in_response = await redirect_if_not_logged_in(
        request, redirect_path=frontend_router.url_path_for("configure_todoist")
    )
    if isinstance(logged_in_response, Response):
        return logged_in_response

    user = logged_in_response
    return create_todoist_config_template(request, user)


@frontend_router.post("", response_class=HTMLResponse)
async def update_todoist_configuration(
    request: Request,
    config_input: UserTodoistConfigurationUpdate = Depends(UserTodoistConfigurationUpdate.as_form),
):
    logged_in_response = await redirect_if_not_logged_in(
        request,
        redirect_path=frontend_router.url_path_for("configure_todoist"),
    )

    if isinstance(logged_in_response, Response):
        return logged_in_response

    user = logged_in_response
    try:
        await update_todoist_account_link(user, config_input)
        return create_todoist_config_template(
            request,
            user,
            success_message="Configuration successfully updated",
        )

    except Exception:
        return create_todoist_config_template(
            request,
            user,
            auth_error="Oops, something went wrong! Unable to update your configuration",
        )


@frontend_router.post("/unlink")
async def delete_todoist_config(request: Request):
    """Delete the user's Todoist authorization"""

    logged_in_response = await redirect_if_not_logged_in(
        request,
        redirect_path=frontend_router.url_path_for("configure_todoist"),
    )

    if isinstance(logged_in_response, Response):
        return logged_in_response

    user = logged_in_response
    try:
        user = await unlink_todoist_account(user)
        return create_todoist_config_template(
            request,
            user,
            success_message="Successfully unlinked your Todoist account",
        )

    except Exception:
        return create_todoist_config_template(
            request,
            user,
            auth_error="Unknown error when trying to unlink your account",
        )


@frontend_router.get("/authorize-todoist", response_class=RedirectResponse)
async def redirect_to_todoist_auth_request(request: Request):
    """Redirect the user to Todoist to begin Todoist authorization"""

    logged_in_response = await redirect_if_not_logged_in(
        request,
        redirect_path=frontend_router.url_path_for("configure_todoist"),
    )

    if isinstance(logged_in_response, Response):
        return logged_in_response

    state = str(uuid4())
    request_params = TodoistAuthRequest(client_id=secrets.todoist_client_id, scope=settings.todoist_scope, state=state)

    req = PreparedRequest()
    req.prepare_url(settings.todoist_auth_request_url, request_params.dict())
    redirect_url = cast(str, req.url)

    response = RedirectResponse(redirect_url)
    response.set_cookie(TODOIST_STATE_COOKIE, state, httponly=True)
    return response


### Auth Handshake ###


@auth_router.get("")
async def authorize_todoist(request: Request, auth: TodoistRedirect = Depends()):
    """The authorization URI for Todoist account linking"""

    logged_in_response = await redirect_if_not_logged_in(
        request, redirect_path=auth_router.url_path_for("authorize_todoist"), params=auth.dict(exclude_none=True)
    )

    if isinstance(logged_in_response, Response):
        return logged_in_response

    user = logged_in_response

    if auth.error or request.cookies.get(TODOIST_STATE_COOKIE) != auth.state:
        return create_todoist_config_template(request, user, auth_error="Unable to link to your Todoist account")

    try:
        params = TodoistTokenExchangeRequest(
            client_id=secrets.todoist_client_id, client_secret=secrets.todoist_client_secret, code=auth.code
        )

        r = requests.post(settings.todoist_token_exchange_url, params=params.dict())
        r.raise_for_status()
        token_response = TodoistTokenResponse.parse_obj(r.json())

        user.configuration.todoist = link_todoist_account(
            user, UserTodoistConfigurationCreate(access_token=token_response.access_token)
        )

        return create_todoist_config_template(request, user, success_message="Successfully linked your Todoist account")

    except (HTTPError, JSONDecodeError, ValidationError):
        return create_todoist_config_template(request, user, auth_error="Unable to link to your Todoist account")

    except Exception:
        return create_todoist_config_template(
            request, user, auth_error="Unknown error when trying to link your Todoist account"
        )
