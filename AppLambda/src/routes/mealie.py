from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse

from ..app import templates
from ..models.account_linking import (
    UserMealieConfigurationCreate,
    UserMealieConfigurationUpdate,
)
from ..models.core import User
from .account_linking import (
    link_mealie_account,
    unlink_mealie_account,
    update_mealie_account_link,
)
from .core import redirect_if_not_logged_in

router = APIRouter(prefix="/app/mealie", tags=["Mealie"])

### Frontend ###


def create_mealie_config_template(request: Request, user: User, **kwargs):
    context = {
        "request": request,
        "user": user,
    }

    return templates.TemplateResponse(
        "mealie_config.html",
        {**context, **{k: v for k, v in kwargs.items() if k not in context}},
    )


@router.get("", response_class=HTMLResponse)
async def configure_mealie(request: Request):
    """Render the Mealie authorization page"""

    logged_in_response = await redirect_if_not_logged_in(
        request,
        redirect_path=router.url_path_for("configure_mealie"),
    )

    if isinstance(logged_in_response, Response):
        return logged_in_response

    user = logged_in_response
    response = create_mealie_config_template(request, user)
    return response


@router.post("/create-link")
async def create_mealie_configuration(
    request: Request,
    mealie_config_input: UserMealieConfigurationCreate = Depends(UserMealieConfigurationCreate.as_form),
):
    logged_in_response = await redirect_if_not_logged_in(
        request,
        redirect_path=router.url_path_for("configure_mealie"),
    )

    if isinstance(logged_in_response, Response):
        return logged_in_response

    user = logged_in_response
    try:
        link_mealie_account(request, user, mealie_config_input)
        return create_mealie_config_template(
            request,
            user,
            success_message="Configuration successfully updated",
        )

    except Exception:
        return create_mealie_config_template(
            request,
            user,
            auth_error="Unable to connect to your Mealie instance. Please check your information and try again",
        )


@router.post("/update-link")
async def update_mealie_configuration(
    request: Request,
    config_input: UserMealieConfigurationUpdate = Depends(UserMealieConfigurationUpdate.as_form),
):
    logged_in_response = await redirect_if_not_logged_in(
        request,
        redirect_path=router.url_path_for("configure_mealie"),
    )

    if isinstance(logged_in_response, Response):
        return logged_in_response

    user = logged_in_response
    try:
        update_mealie_account_link(user, config_input)
        return create_mealie_config_template(
            request,
            user,
            success_message="Configuration successfully updated",
        )

    except Exception:
        return create_mealie_config_template(
            request,
            user,
            auth_error="Oops, something went wrong! Unable to update your configuration",
        )


@router.post("/delete-link")
async def delete_mealie_configuration(request: Request):
    logged_in_response = await redirect_if_not_logged_in(
        request,
        redirect_path=router.url_path_for("configure_mealie"),
    )

    if isinstance(logged_in_response, Response):
        return logged_in_response

    # TODO: handle exceptions
    user = logged_in_response
    try:
        user = unlink_mealie_account(user)
        return create_mealie_config_template(
            request,
            user,
            success_message="Successfully unlinked from Mealie",
        )

    except Exception:
        return create_mealie_config_template(
            request,
            user,
            auth_error="Oops, something went wrong! Unable to unlink your configuration",
        )
