import inspect
import re
from collections import defaultdict
from enum import Enum
from typing import Any, Callable, Optional, TypeVar, Union, cast
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
    MealieShoppingListItemsCollectionOut,
    MealieShoppingListItemUpdate,
    MealieShoppingListRecipeRef,
    Unit,
)

T = TypeVar("T")


class MockDBKey(Enum):
    foods = "foods"
    labels = "labels"
    notifiers = "notifiers"
    recipes = "recipes"
    shopping_lists = "shopping_lists"
    shopping_list_items = "shopping_list_items"
    units = "units"
    user_api_tokens = "user_api_tokens"


class MockMealieServer:
    def __init__(self) -> None:
        self.group_id = str(uuid4())
        self.db: defaultdict[MockDBKey, dict[str, dict[str, Any]]] = defaultdict(dict[str, dict[str, Any]])

    @classmethod
    def _get_id_from_endpoint(cls, endpoint: str) -> str:
        return endpoint.split("/")[-1]

    @classmethod
    def _assert_or_404(cls, data: Optional[T]) -> T:
        if not data:
            response = Response()
            response.status_code = 404
            raise HTTPError(response=response)

        return data

    def _validate_headers(self, headers: Optional[dict]) -> dict:

        try:
            assert headers
            auth_header = headers.get("Authorization")
            assert auth_header and isinstance(auth_header, str)

            bearer, token = auth_header.split()
            assert bearer == "Bearer"
            assert token

            valid_tokens: set[str] = set(
                auth_token["token"]
                for auth_token in self.db[MockDBKey.user_api_tokens].values()
                if "token" in auth_token
            )
            assert token in valid_tokens

        except Exception as e:
            response = Response()
            response.status_code = 401
            raise HTTPError(response=response) from e

        return headers

    def _insert_one(self, key: MockDBKey, id: str, data: dict[str, Any]) -> None:
        self.db[key][id] = data

    def _get_all(self, key: MockDBKey) -> list[dict[str, Any]]:
        return list(self.db[key].values())

    def _get_one(self, key: MockDBKey, id_or_endpoint: str) -> dict[str, Any]:
        id = self._get_id_from_endpoint(id_or_endpoint)
        data = self._assert_or_404(self.db[key].get(id))
        return data

    def _delete_one(self, key: MockDBKey, id_or_endpoint: str) -> dict[str, Any]:
        id = self._get_id_from_endpoint(id_or_endpoint)
        data = self._assert_or_404(self.db[key].pop(id, None))
        return data

    def _create_notifier(self, payload: dict[str, Any]) -> dict[str, Any]:
        notifier = MealieEventNotifierCreate(**payload)
        notifier_out = notifier.cast(MealieEventNotifierOut, id=str(uuid4()), group_id=self.group_id)
        data = notifier_out.dict()

        self._insert_one(MockDBKey.notifiers, notifier_out.id, data)
        return data

    def _update_notifier(self, id_or_endpoint: str) -> dict[str, Any]:
        # we don't track updates to notifiers
        return self._get_one(MockDBKey.notifiers, id_or_endpoint)

    def _create_shopping_list_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        item = MealieShoppingListItemCreate(**payload)
        id = str(uuid4())

        food = Food(**self._assert_or_404(self.db[MockDBKey.foods].get(item.food_id))) if item.food_id else None
        label = Label(**self._assert_or_404(self.db[MockDBKey.labels].get(item.label_id))) if item.label_id else None
        unit = Unit(**self._assert_or_404(self.db[MockDBKey.units].get(item.unit_id))) if item.unit_id else None
        recipe_references = [
            ref.cast(MealieShoppingListRecipeRef, id=str(uuid4()), shopping_list_item_id=id)
            for ref in item.recipe_references
        ]

        item_out = item.cast(
            MealieShoppingListItemOut,
            id=id,
            display=id,
            food=food,
            label=label,
            unit=unit,
            recipe_references=recipe_references,
        )
        data = item_out.dict()
        self._insert_one(MockDBKey.shopping_list_items, id, data)

        # insert list item into shopping list
        shopping_list = self.db[MockDBKey.shopping_lists].get(item_out.shopping_list_id)
        assert shopping_list
        assert "list_items" in shopping_list
        shopping_list["list_items"].append(data)

        return data

    def _update_shopping_list_item(self, id: str, payload: dict[str, Any]) -> dict[str, Any]:
        update_item = MealieShoppingListItemUpdate(**payload)
        update_item_data = update_item.dict()
        existing_item_data = self._get_one(MockDBKey.shopping_list_items, id)
        for key in existing_item_data:
            if key in update_item_data:
                existing_item_data[key] = update_item_data[key]

        self._insert_one(MockDBKey.shopping_list_items, id, existing_item_data)

        # update list item in shopping list
        shopping_list = self.db[MockDBKey.shopping_lists].get(update_item.shopping_list_id)
        assert shopping_list

        list_items_data = cast(Optional[list[dict[str, Any]]], shopping_list.get("list_items"))
        assert list_items_data

        assert id in set(li.get("id") for li in list_items_data)
        new_list_items_data = [existing_item_data if li.get("id") == id else li for li in list_items_data]
        self.db[MockDBKey.shopping_lists][update_item.shopping_list_id]["list_items"] = new_list_items_data

        return existing_item_data

    def _delete_shopping_list_item(self, id: str) -> dict[str, Any]:
        deleted_item_data = self._delete_one(MockDBKey.shopping_list_items, id)

        # remove item from shopping list
        item = MealieShoppingListItemOut(**deleted_item_data)
        shopping_list_data = self.db[MockDBKey.shopping_lists].get(item.shopping_list_id)
        assert shopping_list_data

        list_items_data = cast(Optional[list[dict[str, Any]]], shopping_list_data.get("list_items"))
        assert list_items_data

        new_list_items_data = [li for li in list_items_data if not li.get("id") == item.id]
        assert len(new_list_items_data) < len(list_items_data)
        self.db[MockDBKey.shopping_lists][item.shopping_list_id]["list_items"] = new_list_items_data

        return deleted_item_data

    def _create_user_api_token(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert "name" in payload
        token = AuthToken(id=uuid4(), name=payload["name"], token=str(uuid4()))
        data = token.dict()

        self._insert_one(MockDBKey.user_api_tokens, token.id, data)
        return data

    def handle_request(
        self,
        method: str,
        endpoint: str,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        payload: Optional[Union[list, dict]] = None,
    ) -> Response:
        """Routes an HTTP request to a mock function"""

        headers = self._validate_headers(headers)
        params = params or {}
        payload = payload or {}

        try:

            def is_route(route: Union[str, Callable]) -> bool:
                if isinstance(route, str):
                    return route == endpoint

                args = [".*"] * len(inspect.signature(route).parameters)
                return bool(re.compile(route(*args)).match(endpoint))

            method = method.upper()
            data: Optional[Union[str, list, dict]] = None
            if is_route(Routes.FOODS):
                if method == "GET":
                    data = self._get_all(MockDBKey.foods)

            elif is_route(Routes.GROUPS_EVENTS_NOTIFICATIONS):
                if method == "POST":
                    assert isinstance(payload, dict)
                    data = self._create_notifier(payload)

            elif is_route(Routes.GROUPS_EVENTS_NOTIFICATIONS_NOTIFICATION_ID):
                if method == "PUT":
                    data = self._update_notifier(endpoint)

                elif method == "DELETE":
                    data = self._delete_one(MockDBKey.notifiers, endpoint)

            elif is_route(Routes.GROUPS_LABELS):
                if method == "GET":
                    data = self._get_all(MockDBKey.labels)

            elif is_route(Routes.GROUPS_SHOPPING_LISTS):
                if method == "GET":
                    data = self._get_all(MockDBKey.shopping_lists)

            elif is_route(Routes.GROUPS_SHOPPING_LISTS_SHOPPING_LIST_ID):
                if method == "GET":
                    data = self._get_one(MockDBKey.shopping_lists, endpoint)

            elif is_route(Routes.GROUPS_SHOPPING_ITEMS):
                if method == "GET":
                    data = self._get_all(MockDBKey.shopping_list_items)

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
                    data = self._get_all(MockDBKey.recipes)

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
                    data = self._get_one(MockDBKey.user_api_tokens, endpoint)

            if data is not None:
                response = Response()
                response.json = lambda: data  # type: ignore
                return response

            else:
                raise NotImplementedError()

        except HTTPError as e:
            return e.response