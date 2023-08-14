import json
import logging
import random
import string
from typing import cast

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from todoist_api_python.api import TodoistAPI

from ..app import app, services, settings, templates
from ..clients.mealie import MealieClient
from ..models.account_linking import (
    SyncMapRender,
    SyncMapRenderList,
    UserAlexaConfiguration,
    UserAlexaConfigurationCreate,
    UserMealieConfiguration,
    UserMealieConfigurationCreate,
    UserMealieConfigurationUpdate,
    UserTodoistConfiguration,
    UserTodoistConfigurationCreate,
    UserTodoistConfigurationUpdate,
)
from ..models.core import ListSyncMap, RateLimitCategory, Source, User
from ..models.mealie import MealieEventNotifierOptions, MealieEventNotifierUpdate
from ..services.alexa import AlexaListService
from ..services.mealie import MealieListService
from .auth import get_current_user
from .core import redirect_if_not_logged_in

frontend_router = APIRouter(prefix="/app/map-shopping-lists", tags=["Account Linking"])
api_router = APIRouter(prefix="/api/account-linking", tags=["Account Linking"])


def _get_todoist_client(token: str) -> TodoistAPI:
    return TodoistAPI(token)


### Frontend ###
async def create_shopping_list_sync_map_template(request: Request, user: User, **kwargs):
    context = {
        "request": request,
        "user": user,
    }

    if not user.is_linked_to_mealie:
        return templates.TemplateResponse(
            "list_sync_mapping.html",
            {**context, **{k: v for k, v in kwargs.items() if k not in context}},
        )

    mealie_service = MealieListService(user)
    context["mealie_lists"] = [
        SyncMapRender(list_id=mealie_list.id, list_name=mealie_list.name, selected=True)
        for mealie_list in mealie_service.get_all_lists()
    ]

    # assemble all lists from all linked accounts
    linked_accounts: dict[Source, SyncMapRenderList] = {}
    link_errors: list[str] = []
    if user.is_linked_to_alexa:
        try:
            alexa_service = AlexaListService(user)
            alexa_list_collection = alexa_service.get_all_lists()

            existing_links = {
                list_sync_map.alexa_list_id: mealie_list_id
                for mealie_list_id, list_sync_map in user.list_sync_maps.items()
                if list_sync_map.alexa_list_id
            }

            linked_accounts[Source.alexa] = SyncMapRenderList(
                column_header="Alexa List",
                lists=[
                    SyncMapRender(
                        list_id=alexa_list.list_id,
                        list_name=alexa_list.name,
                        selected_mealie_list_id=existing_links.get(alexa_list.list_id),
                    )
                    for alexa_list in alexa_list_collection.lists
                ],
            )

        except Exception as e:
            logging.error(f"Unhandled exception when trying to pull alexa lists for {user.username}")
            logging.error(f"{type(e).__name__}: {e}")
            link_errors.append("Something went wrong when trying to connect to Alexa")

    if user.is_linked_to_todoist:
        try:
            todoist_config = cast(UserTodoistConfiguration, user.configuration.todoist)
            todoist_client = _get_todoist_client(todoist_config.access_token)
            todoist_projects = todoist_client.get_projects()

            existing_links = {
                list_sync_map.todoist_project_id: mealie_list_id
                for mealie_list_id, list_sync_map in user.list_sync_maps.items()
                if list_sync_map.todoist_project_id
            }

            linked_accounts[Source.todoist] = SyncMapRenderList(
                column_header="Todoist Project",
                lists=[
                    SyncMapRender(
                        list_id=project.id,
                        list_name=project.name,
                        selected_mealie_list_id=existing_links.get(project.id),
                    )
                    for project in todoist_projects
                ],
            )

        except Exception as e:
            logging.error(f"Unhandled exception when trying to pull todoist projects for {user.username}")
            logging.error(f"{type(e).__name__}: {e}")
            link_errors.append("Something went wrong when trying to connect to Todoist")

    context["linked_accounts"] = linked_accounts
    context["show_unidirectional_sync_footnote"] = any([link.is_unidirectional for link in linked_accounts.values()])
    context["errors"] = link_errors
    return templates.TemplateResponse(
        "list_sync_mapping.html",
        {**context, **{k: v for k, v in kwargs.items() if k not in context}},
    )


@frontend_router.get("", response_class=HTMLResponse)
async def configure_shopping_list_sync_maps(request: Request):
    """Render the shopping list sync map page"""

    logged_in_response = await redirect_if_not_logged_in(
        request,
        redirect_path=frontend_router.url_path_for("configure_shopping_list_sync_maps"),
    )

    if isinstance(logged_in_response, Response):
        return logged_in_response

    user = logged_in_response
    if not user.is_linked_to_mealie:
        return RedirectResponse(app.url_path_for("configure_mealie"))

    response = await create_shopping_list_sync_map_template(request, user)
    return response


@frontend_router.post("", response_class=HTMLResponse)
async def handle_sync_map_update_form(request: Request, list_map_data: list[str] = Form(..., alias="listMapData")):
    logged_in_response = await redirect_if_not_logged_in(
        request,
        redirect_path=frontend_router.url_path_for("configure_shopping_list_sync_maps"),
    )

    if isinstance(logged_in_response, Response):
        return logged_in_response

    user = logged_in_response

    try:
        # list map data comes in a list of JSON strings. If the user did not link a particular list, the string is empty
        # we parse the strings into dictionaries, then combine the dictionaries using the mealie list id

        # ["{mealie_list_id: {Source.value: external_list.id}}"]
        parsed_list_data: list[dict[str, dict[str, str]]] = [json.loads(data) for data in list_map_data if data]

        seen_list_links: set[str] = set()
        combined_list_data: dict[str, dict[Source, str]] = {}

        # [{mealie_list_id: {Source.value: external_list.id}}]
        for list_data in parsed_list_data:
            # {mealie_list_id: {Source.value: external_list.id}}
            for mealie_list_id, external_list_data in list_data.items():
                list_link_signature = json.dumps(external_list_data)
                if list_link_signature in seen_list_links:
                    continue

                # make sure each Mealie list -> external system map is unique
                seen_list_links.add(list_link_signature)

                # {Source.value: external_list.id}
                for source_value, external_list_id in external_list_data.items():
                    combined_list_data.setdefault(mealie_list_id, {})[Source(source_value)] = external_list_id

        user.list_sync_maps = {
            mealie_shopping_list_id: ListSyncMap(
                mealie_shopping_list_id=mealie_shopping_list_id,
                alexa_list_id=external_lists.get(Source.alexa),
                todoist_project_id=external_lists.get(Source.todoist),
            )
            for mealie_shopping_list_id, external_lists in combined_list_data.items()
        }

        services.user.update_user(user)
        return await create_shopping_list_sync_map_template(
            request, user, success_message="Successfully updated shopping list maps"
        )

    except Exception:
        return await create_shopping_list_sync_map_template(
            request,
            user,
            errors=["Something went wrong, unable to update your shopping list maps"],
        )


### API ###


@api_router.post("/alexa", response_model=UserAlexaConfiguration, tags=["Alexa"], include_in_schema=False)
@services.rate_limit.limit(RateLimitCategory.modify)
async def link_alexa_account(
    user: User = Depends(get_current_user),
    alexa_config_input: UserAlexaConfigurationCreate = Depends(),
) -> UserAlexaConfiguration:
    user.alexa_user_id = alexa_config_input.user_id
    user.configuration.alexa = alexa_config_input.cast(UserAlexaConfiguration)
    services.user.update_user(user)
    return user.configuration.alexa


@api_router.delete("/alexa", tags=["Alexa"])
@services.rate_limit.limit(RateLimitCategory.modify)
async def unlink_alexa_account(user: User = Depends(get_current_user)) -> User:
    # TODO: send unlink request to Alexa; currently this just removes the id from the database
    user.alexa_user_id = None
    user.configuration.alexa = None
    services.user.update_user(user)
    return user


@api_router.post("/mealie", response_model=UserMealieConfiguration, tags=["Mealie"])
@services.rate_limit.limit(RateLimitCategory.modify)
async def link_mealie_account(
    request: Request,
    user: User = Depends(get_current_user),
    config_input: UserMealieConfigurationCreate = Depends(),
) -> UserMealieConfiguration:
    client = MealieClient(config_input.base_url, config_input.initial_auth_token)
    if not client.is_valid:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Invalid Mealie configuration. Please check your base URL and auth token",
        )

    new_mealie_token = client.create_auth_token(f"{app.title} | {user.username}", settings.mealie_integration_id)

    # create a new notifier
    base_url = str(request.base_url).replace("https://", "").replace("http://", "")[:-1]
    full_notifier_path = base_url + app.url_path_for("mealie_event_notification_handler")

    security_hash = "".join(random.choices(string.ascii_letters + string.digits, k=8))

    notifier_url = settings.mealie_apprise_notifier_url_template.format(
        full_path=full_notifier_path,
        username=user.username,
        security_hash=security_hash,
    )

    new_mealie_notifier = client.create_notifier(f"{app.title} | {user.username}", notifier_url)

    # update the notifier to only send us shopping list updates
    updated_notifier = MealieEventNotifierUpdate(
        id=new_mealie_notifier.id,
        group_id=new_mealie_notifier.group_id,
        name=new_mealie_notifier.name,
        apprise_url=notifier_url,
        options=MealieEventNotifierOptions(shopping_list_updated=True),
    )

    client.update_notifier(updated_notifier)

    user.configuration.mealie = UserMealieConfiguration(
        base_url=config_input.base_url,
        auth_token=new_mealie_token.token,
        auth_token_id=new_mealie_token.id,
        notifier_id=new_mealie_notifier.id,
        security_hash=security_hash,
    )

    services.user.update_user(user)
    return user.configuration.mealie


@api_router.put("/mealie", response_model=UserMealieConfiguration, tags=["Mealie"])
@services.rate_limit.limit(RateLimitCategory.modify)
async def update_mealie_account_link(
    user: User = Depends(get_current_user),
    mealie_config: UserMealieConfigurationUpdate = Depends(),
) -> UserMealieConfiguration:
    if not user.configuration.mealie:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User is not linked to Mealie")

    user.configuration.mealie.use_foods = mealie_config.use_foods
    user.configuration.mealie.overwrite_original_item_names = mealie_config.overwrite_original_item_names
    user.configuration.mealie.confidence_threshold = mealie_config.confidence_threshold

    services.user.update_user(user)
    return user.configuration.mealie


@api_router.delete("/mealie", tags=["Mealie"])
@services.rate_limit.limit(RateLimitCategory.modify)
async def unlink_mealie_account(user: User = Depends(get_current_user)) -> User:
    mealie_config = user.configuration.mealie
    if not mealie_config:
        return user

    # remove the auth token and notifier that we created
    client = MealieClient(mealie_config.base_url, mealie_config.auth_token)
    try:
        client.delete_notifier(mealie_config.notifier_id)

    except Exception:
        pass

    try:
        client.delete_auth_token(mealie_config.auth_token_id)

    except Exception:
        pass

    user.configuration.mealie = None
    services.user.update_user(user)
    return user


# this is not included in the schema because it should only be called directly by Todoist
@api_router.post("/todoist", response_model=UserTodoistConfiguration, tags=["Todoist"], include_in_schema=False)
@services.rate_limit.limit(RateLimitCategory.modify)
async def link_todoist_account(
    user: User = Depends(get_current_user),
    config_input: UserTodoistConfigurationCreate = Depends(),
) -> UserTodoistConfiguration:
    client = _get_todoist_client(config_input.access_token)

    try:
        # there is no endpoint for fetching a user's id, so we read a task from the inbox
        user_id = ""
        projects = client.get_projects()
        for project in projects:
            if not project.is_inbox_project:
                continue

            tasks = client.get_tasks(project_id=project.id)
            if tasks:
                user_id = tasks[0].creator_id
                break

            # if there are no tasks, we must create a temporary one
            temporary_task = client.add_task(f"Sync to {settings.app_title}")
            user_id = temporary_task.creator_id
            client.delete_task(temporary_task.id)
            break

        if not user_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Could not determine Todoist user_id")

    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Could not connect to Todoist") from e

    user.todoist_user_id = user_id
    user.configuration.todoist = UserTodoistConfiguration(access_token=config_input.access_token)

    services.user.update_user(user)
    return user.configuration.todoist


@api_router.put("/todoist", response_model=UserTodoistConfiguration, tags=["Todoist"])
@services.rate_limit.limit(RateLimitCategory.modify)
async def update_todoist_account_link(
    user: User = Depends(get_current_user), config_input: UserTodoistConfigurationUpdate = Depends()
) -> UserTodoistConfiguration:
    if not user.is_linked_to_todoist:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User is not linked to Todoist")

    todoist_config = cast(UserTodoistConfiguration, user.configuration.todoist)
    todoist_config.map_labels_to_sections = config_input.map_labels_to_sections
    todoist_config.default_section_name = config_input.default_section_name
    todoist_config.add_recipes_to_task_description = config_input.add_recipes_to_task_description

    user.configuration.todoist = todoist_config
    services.user.update_user(user)
    return user.configuration.todoist


@api_router.delete("/todoist", tags=["Todoist"])
@services.rate_limit.limit(RateLimitCategory.modify)
async def unlink_todoist_account(user: User = Depends(get_current_user)) -> User:
    user.todoist_user_id = None
    user.configuration.todoist = None
    services.user.update_user(user)
    return user
