import inspect
import math
import re
from collections import defaultdict
from enum import Enum
from typing import Any, Callable, TypeVar, cast
from uuid import uuid4

from requests import HTTPError, Response

from AppLambda.src.clients.mealie import Routes
from AppLambda.src.models.mealie import (
    AuthToken,
    Food,
    Label,
    MealieEventNotifierCreate,
    MealieEventNotifierOut,
    MealieShoppingListItemCreate,
    MealieShoppingListItemOut,
    MealieShoppingListItemRecipeRefOut,
    MealieShoppingListItemsCollectionOut,
    MealieShoppingListItemUpdate,
    Pagination,
    Unit,
)
from tests.utils.generators import random_url

T = TypeVar("T")


class MockMealieDBKey(Enum):
    foods = "foods"
    labels = "labels"
    notifiers = "notifiers"
    recipes = "recipes"
    shopping_lists = "shopping_lists"
    units = "units"
    user_api_tokens = "user_api_tokens"


# TODO: refactor to use actual models instead of dictionaries


class MockMealieServer:
    def __init__(self) -> None:
        self.base_url = random_url()
        self.group_id = str(uuid4())
        self.db: defaultdict[MockMealieDBKey, dict[str, dict[str, Any]]] = defaultdict(dict[str, dict[str, Any]])
        self.headers: dict[str, str] = {}

    @classmethod
    def _get_id_from_url(cls, url: str) -> str:
        return url.split("/")[-1]

    @classmethod
    def _assert(cls, data: T | None) -> T:
        if not data:
            response = Response()
            response.status_code = 404
            raise HTTPError(response=response)

        return data

    def _validate_headers(self, headers: dict | None) -> dict:
        if headers is None:
            headers = {}

        headers.update(self.headers)
        try:
            auth_header = headers.get("Authorization")
            assert auth_header and isinstance(auth_header, str)

            bearer, token = auth_header.split()
            assert bearer == "Bearer"
            assert token

            valid_tokens: set[str] = set(
                auth_token["token"]
                for auth_token in self.db[MockMealieDBKey.user_api_tokens].values()
                if "token" in auth_token
            )
            assert token in valid_tokens

        except Exception as e:
            response = Response()
            response.status_code = 401
            raise HTTPError(response=response) from e

        return headers

    def _insert_one(self, key: MockMealieDBKey, id: str, data: dict[str, Any]) -> None:
        self.db[key][id] = data

    def _paginate(self, items: list[dict[str, Any]], params: dict[str, Any]) -> Pagination:
        page = params.get("page", 1)
        assert isinstance(page, int)
        per_page = params.get("perPage", 10)
        assert isinstance(per_page, int)

        total = len(items)
        if page == -1:
            start = 0
            end = -1
            has_more = False
        else:
            start = (page - 1) * per_page
            end = page * per_page
            has_more = end < len(items)

        items = items[start:end] if start < len(items) else []
        pagination = Pagination(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=math.ceil(total / per_page),
            items=items,
            next="placeholder" if has_more else None,
            previous="placeholder" if page > 1 else None,
        )

        return pagination

    def _get_all(self, key: MockMealieDBKey, params: dict[str, Any]) -> dict[str, Any]:
        items = list(self.db[key].values())
        return self._paginate(items, params).dict()

    def _get_one(self, key: MockMealieDBKey, id_or_url: str) -> dict[str, Any]:
        id = self._get_id_from_url(id_or_url)
        data = self._assert(self.db[key].get(id))
        return data

    def _delete_one(self, key: MockMealieDBKey, id_or_url: str) -> dict[str, Any]:
        id = self._get_id_from_url(id_or_url)
        data = self._assert(self.db[key].pop(id, None))
        return data

    def _create_notifier(self, payload: dict[str, Any]) -> dict[str, Any]:
        notifier = MealieEventNotifierCreate(**payload)
        notifier_out = notifier.cast(MealieEventNotifierOut, id=str(uuid4()), group_id=self.group_id)
        data = notifier_out.dict()

        self._insert_one(MockMealieDBKey.notifiers, notifier_out.id, data)
        return data

    def _update_notifier(self, id_or_url: str) -> dict[str, Any]:
        # we don't track updates to notifiers
        return self._get_one(MockMealieDBKey.notifiers, id_or_url)

    def _get_all_shopping_list_items(
        self, shopping_list_id: str, include_checked: bool, params: dict[str, Any]
    ) -> dict[str, Any]:
        shopping_list = self._get_one(MockMealieDBKey.shopping_lists, shopping_list_id)
        list_items = cast(list[dict[str, Any]], shopping_list["list_items"])
        if not include_checked:
            list_items = [li for li in list_items if not li["checked"]]

        return self._paginate(list_items, params).dict()

    def _create_shopping_list_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        item = MealieShoppingListItemCreate(**payload)
        id = str(uuid4())

        food = Food(**self._assert(self.db[MockMealieDBKey.foods].get(item.food_id))) if item.food_id else None
        label = Label(**self._assert(self.db[MockMealieDBKey.labels].get(item.label_id))) if item.label_id else None
        unit = Unit(**self._assert(self.db[MockMealieDBKey.units].get(item.unit_id))) if item.unit_id else None
        recipe_references = [
            ref.cast(MealieShoppingListItemRecipeRefOut, id=str(uuid4()), shopping_list_item_id=id)
            for ref in item.recipe_references
        ]

        item_out = item.cast(
            MealieShoppingListItemOut,
            id=id,
            display=item.note if item.note else "",
            food=food,
            label=label,
            unit=unit,
            recipe_references=recipe_references,
        )
        data = item_out.dict()

        # insert list item into shopping list
        shopping_list = self.db[MockMealieDBKey.shopping_lists].get(item_out.shopping_list_id)
        assert shopping_list
        assert "list_items" in shopping_list
        shopping_list["list_items"].append(data)

        return data

    def _update_shopping_list_item(self, id: str, payload: dict[str, Any]) -> dict[str, Any]:
        update_item = MealieShoppingListItemUpdate(**payload)
        update_item_data = update_item.dict()

        shopping_list = self._get_one(MockMealieDBKey.shopping_lists, update_item.shopping_list_id)
        list_items_data = cast(list[dict[str, Any]] | None, shopping_list.get("list_items"))
        assert list_items_data

        item_data: dict[str, Any] | None = None
        for i, li in enumerate(list_items_data):
            if id != li.get("id"):
                continue

            # merge updated data into item
            for key in update_item_data:
                if key in li:
                    if key == "recipe_references":
                        # this prevents updates to recipe references, but
                        # we don't do that in the app, so it's fine
                        continue

                    li[key] = update_item_data[key]

            # update display
            li["display"] = li["note"] if li["note"] else ""

            # update ORM links
            for db_key, link in [
                (MockMealieDBKey.foods, "food"),
                (MockMealieDBKey.labels, "label"),
                (MockMealieDBKey.units, "unit"),
            ]:
                link_id = li.get(f"{link}_id")
                if link_id is None:
                    li[link] = None

                else:
                    li[link] = self._get_one(db_key, link_id)

            # save changes
            list_items_data[i] = li
            item_data = li
            break

        assert item_data
        self.db[MockMealieDBKey.shopping_lists][update_item.shopping_list_id]["list_items"] = list_items_data
        return item_data

    def _delete_shopping_list_item(self, item_id: str) -> dict[str, Any]:
        shopping_lists = self.get_all_records(MockMealieDBKey.shopping_lists)
        deleted_item_data: dict[str, Any] | None = None
        for shopping_list in shopping_lists.values():
            list_items_data = cast(list[dict[str, Any]], shopping_list["list_items"])
            for i, li in enumerate(list_items_data):
                if item_id != li.get("id"):
                    continue

                # store the deleted item data and remove it from the shopping list
                deleted_item_data = li
                del self.db[MockMealieDBKey.shopping_lists][li["shopping_list_id"]]["list_items"][i]
                break

            if deleted_item_data:
                break

        assert deleted_item_data
        return deleted_item_data

    def _create_user_api_token(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert "name" in payload
        token = AuthToken(id=str(uuid4()), name=payload["name"], token=str(uuid4()))
        data = token.dict()

        self._insert_one(MockMealieDBKey.user_api_tokens, token.id, data)
        return data

    def get_all_records(self, record_type: MockMealieDBKey) -> dict[str, dict[str, Any]]:
        """
        Fetch all records by record type

        Bypasses normal mock HTTP validation
        """

        return self.db[record_type]

    def get_record_by_id(self, record_type: MockMealieDBKey, id: str) -> dict[str, Any] | None:
        """
        Fetch a single record by id and record type, if it exists

        Bypasses normal mock HTTP validation
        """

        return self.get_all_records(record_type).get(id)

    def request(
        self,
        method: str,
        url: str,
        headers: dict | None = None,
        params: dict | None = None,
        json: list | dict | None = None,
        *args,
        **kwargs,
    ) -> Response:
        """Routes an HTTP request to a mock function"""

        headers = self._validate_headers(headers)
        params = params or {}
        payload = json or {}

        def is_route(route: str | Callable) -> bool:
            endpoint = url[len(self.base_url) :]  # all random URLs are the same length
            if isinstance(route, str):
                return route == endpoint

            args = [".*"] * len(inspect.signature(route).parameters)
            return bool(re.compile(route(*args)).match(endpoint))

        try:
            method = method.upper()
            data: str | list | dict | None = None
            if is_route(Routes.FOODS):
                if method == "GET":
                    data = self._get_all(MockMealieDBKey.foods, params)

            elif is_route(Routes.GROUPS_EVENTS_NOTIFICATIONS):
                if method == "POST":
                    assert isinstance(payload, dict)
                    data = self._create_notifier(payload)

            elif is_route(Routes.GROUPS_EVENTS_NOTIFICATIONS_NOTIFICATION_ID):
                if method == "PUT":
                    data = self._update_notifier(url)

                elif method == "DELETE":
                    data = self._delete_one(MockMealieDBKey.notifiers, url)

            elif is_route(Routes.GROUPS_LABELS):
                if method == "GET":
                    data = self._get_all(MockMealieDBKey.labels, params)

            elif is_route(Routes.GROUPS_SHOPPING_LISTS):
                if method == "GET":
                    data = self._get_all(MockMealieDBKey.shopping_lists, params)

            elif is_route(Routes.GROUPS_SHOPPING_LISTS_SHOPPING_LIST_ID):
                if method == "GET":
                    data = self._get_one(MockMealieDBKey.shopping_lists, url)

            elif is_route(Routes.GROUPS_SHOPPING_ITEMS):
                if method == "GET":
                    assert "queryFilter" in params
                    shopping_list_id: str | None = None
                    include_checked = True

                    filters = cast(list[str], params["queryFilter"].split())
                    for filter in filters:
                        if "shopping_list_id" in filter:
                            shopping_list_id = filter.split("=")[-1]

                        elif "checked" in filter:
                            include_checked = filter.split("=")[-1].lower()[0] == "t"

                    assert shopping_list_id
                    data = self._get_all_shopping_list_items(shopping_list_id, include_checked, params)

                elif method == "PUT":
                    assert isinstance(payload, list)
                    updated_items: list[MealieShoppingListItemOut] = []
                    for item_data in payload:
                        assert "id" in item_data
                        id = item_data.pop("id")
                        updated_items.append(
                            MealieShoppingListItemOut(**self._update_shopping_list_item(id, item_data))
                        )

                    data = MealieShoppingListItemsCollectionOut(updated_items=updated_items).dict()

                elif method == "DELETE":
                    deleted_items = [
                        MealieShoppingListItemOut(**self._delete_shopping_list_item(id)) for id in params.get("ids", [])
                    ]
                    data = MealieShoppingListItemsCollectionOut(deleted_items=deleted_items).dict()

            elif is_route(Routes.GROUPS_SHOPPING_ITEMS_CREATE_BULK):
                if method == "POST":
                    assert isinstance(payload, list)
                    new_items = [
                        MealieShoppingListItemOut(**self._create_shopping_list_item(item_data)) for item_data in payload
                    ]
                    data = MealieShoppingListItemsCollectionOut(created_items=new_items).dict()

            elif is_route(Routes.RECIPES):
                if method == "GET":
                    data = self._get_all(MockMealieDBKey.recipes, params)

            elif is_route(Routes.USERS_SELF):
                if method == "GET":
                    # this route is only used for validation, we don't use the data
                    data = {}

            elif is_route(Routes.USERS_API_TOKENS):
                if method == "POST":
                    assert isinstance(payload, dict)
                    data = self._create_user_api_token(payload)

            elif is_route(Routes.USERS_API_TOKENS_TOKEN_ID):
                if method == "DELETE":
                    data = self._delete_one(MockMealieDBKey.user_api_tokens, url)

            if data is not None:
                response = Response()
                response.json = lambda: data  # type: ignore
                response.status_code = 200
                return response

            else:
                raise NotImplementedError()

        except HTTPError as e:
            return e.response
