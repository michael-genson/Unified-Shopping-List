import base64
import hashlib
import hmac
import logging
from datetime import timedelta
from typing import cast

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from requests import PreparedRequest

from ..app import templates
from ..app_secrets import APP_CLIENT_ID, APP_CLIENT_SECRET
from ..config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ACCESS_TOKEN_EXPIRE_MINUTES_TEMPORARY,
    ALEXA_SECRET_HEADER_KEY,
)
from ..models.alexa import (
    AlexaAuthRequest,
    AlexaReadListCollection,
    AlexaReadListItemCollection,
)
from ..models.core import Source, Token, User
from ..models.mealie import (
    MealieShoppingListItemCreate,
    MealieShoppingListItemExtras,
    MealieSyncEvent,
)
from ..services.mealie import MealieListService
from .account_linking import alexa_list_service, unlink_alexa_account
from .auth import (
    create_access_token,
    get_current_active_user,
    refresh_access_token,
    users_db,
)
from .core import redirect_if_not_logged_in

auth_router = APIRouter(prefix="/authorization/alexa", tags=["Alexa"])
frontend_router = APIRouter(prefix="/app/alexa", tags=["Alexa"])
list_router = APIRouter(prefix="/api/alexa/lists", tags=["Alexa"])
list_item_router = APIRouter(prefix="/api/alexa/lists/items", tags=["Alexa"])


### Frontend ###


def create_alexa_config_template(request: Request, user: User, **kwargs):
    context = {
        "request": request,
        "user": user,
    }

    return templates.TemplateResponse(
        "alexa_config.html",
        {**context, **{k: v for k, v in kwargs.items() if k not in context}},
    )


@frontend_router.get("", response_class=HTMLResponse)
async def configure_alexa(request: Request):
    """Render the Alexa authorization page"""

    logged_in_response = await redirect_if_not_logged_in(
        request,
        redirect_path=frontend_router.url_path_for("configure_alexa"),
    )

    if isinstance(logged_in_response, Response):
        return logged_in_response

    user = logged_in_response
    return create_alexa_config_template(request, user)


@frontend_router.post("/unlink", response_class=HTMLResponse)
async def delete_alexa_config(request: Request):
    """Delete the user's Alexa authorization"""

    logged_in_response = await redirect_if_not_logged_in(
        request,
        redirect_path=frontend_router.url_path_for("configure_alexa"),
    )

    if isinstance(logged_in_response, Response):
        return logged_in_response

    user = logged_in_response

    try:
        user = unlink_alexa_account(user)
        return create_alexa_config_template(
            request,
            user,
            success_message="Successfully unlinked your Alexa account",
        )

    except Exception:
        return create_alexa_config_template(
            request,
            user,
            auth_error="Unknown error when trying to unlink your account",
        )


### Auth Handshake ###


@auth_router.get("")
async def authorize_alexa_app(request: Request, auth: AlexaAuthRequest = Depends()):
    """The authorization URI for Alexa account linking"""

    if auth.client_id != APP_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    logged_in_response = await redirect_if_not_logged_in(
        request,
        redirect_path=auth_router.url_path_for("authorize_alexa_app"),
        params=auth.dict(),
    )

    if isinstance(logged_in_response, Response):
        return logged_in_response

    user = logged_in_response
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES_TEMPORARY)
    user_access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    # add params to redirect uri
    req = PreparedRequest()
    req.prepare_url(auth.redirect_uri, {"code": user_access_token, "state": auth.state})
    redirect_uri = cast(str, req.url)

    return RedirectResponse(redirect_uri, status_code=302)


@auth_router.post("/token", response_model=Token)
def get_access_token(
    grant_type: str = Form(),
    code: str = Form(),
    client_id: str = Form(),
    redirect_uri: str = Form(),
) -> Token:
    """Process Alexa auth-request form and returns an access token"""

    if client_id != APP_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    new_access_token = refresh_access_token(code, expiration_minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    return Token(access_token=new_access_token, token_type="bearer")


@auth_router.delete("/link")
def unlink_user_from_alexa_app(request: Request, user_id: str = Query(..., alias="userId")):
    secret_hash = request.headers.get(ALEXA_SECRET_HEADER_KEY)
    if not secret_hash:
        logging.error("Alexa unlink request received without security hash")
        raise HTTPException(status.HTTP_400_BAD_REQUEST)

    hmac_signature = hmac.new(
        key=APP_CLIENT_SECRET.encode("utf-8"),
        msg=APP_CLIENT_ID.encode("utf-8"),
        digestmod=hashlib.sha256,
    )

    calculated_hash = base64.b64encode(hmac_signature.digest()).decode()
    if calculated_hash != secret_hash:
        logging.error("Alexa unlink request received with invalid hash")
        raise HTTPException(status.HTTP_400_BAD_REQUEST)

    usernames = users_db.get_usernames_by_secondary_index("alexa_user_id", user_id)
    if not usernames:
        return

    for username in usernames:
        _user_in_db = users_db.get_user(username, active_only=False)
        if not _user_in_db:
            continue

        user = _user_in_db.cast(User)
        unlink_alexa_account(user)


### List Management ###


@list_router.get("", response_model=AlexaReadListCollection)
def get_all_lists(
    user: User = Depends(get_current_active_user),
    source: str = "API",
    active_lists_only: bool = True,
) -> AlexaReadListCollection:
    """Fetch all lists from Alexa"""

    if not user.is_linked_to_alexa:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User is not linked to Alexa")

    return alexa_list_service.get_all_lists(user.alexa_user_id, source, active_lists_only)  # type: ignore


@list_item_router.post("", response_model=AlexaReadListItemCollection, include_in_schema=False)
def create_alexa_list_items(
    user: User = Depends(get_current_active_user), items: AlexaReadListItemCollection = Body(...)
) -> AlexaReadListItemCollection:
    """Receive new list items from Alexa"""
    if not user.is_linked_to_mealie:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User is not linked to Mealie")

    alexa_list_items_collection = items
    mealie_list_items: list[MealieShoppingListItemCreate] = []
    mealie_list_ids: set[str] = set()
    for alexa_item in alexa_list_items_collection.list_items:
        # find matching Mealie shopping list
        shopping_list_id = ""
        for list_sync_map in user.list_sync_maps.values():
            if list_sync_map.alexa_list_id == alexa_item.list_id:
                shopping_list_id = list_sync_map.mealie_shopping_list_id
                break

        # if there is no matching list, we don't need to do anything
        if not shopping_list_id:
            continue

        mealie_list_items.append(
            MealieShoppingListItemCreate(
                shopping_list_id=shopping_list_id,
                checked=False,
                quantity=0,  # Alexa does not track quantities, so we explicitly set them to zero
                is_food=False,
                note=alexa_item.value,
                extras=MealieShoppingListItemExtras(
                    original_value=alexa_item.value,
                    alexa_item_id=alexa_item.item_id,
                ),
            )
        )

        mealie_list_ids.add(shopping_list_id)

    if not mealie_list_items:
        return AlexaReadListItemCollection(list_items=[])

    mealie_service = MealieListService(user)
    created_alexa_item_ids: list[str] = []

    for new_item in mealie_list_items:
        try:
            mealie_service.create_item(new_item)
            created_alexa_item_ids.append(new_item.extras.alexa_item_id)  # type: ignore

        except Exception as e:
            logging.error("Unhandled exception when trying to create Alexa item in Mealie")
            logging.error(f"{type(e).__name__}: {e}")
            logging.error(new_item)

    # we ignore callbacks for Mealie events generated by our app, so we need to manually queue up Mealie sync events
    for list_id in mealie_list_ids:
        sync_event = MealieSyncEvent(
            username=user.username, source=Source.mealie, shopping_list_id=list_id
        )

        sync_event.send_to_queue()

    return AlexaReadListItemCollection(
        list_items=[
            item
            for item in alexa_list_items_collection.list_items
            if item.item_id in created_alexa_item_ids
        ]
    )
