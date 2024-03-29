import time
from collections import deque
from typing import Any, Iterable

import requests
from requests import HTTPError, Response

from ..models.mealie import (
    AuthToken,
    Food,
    Label,
    MealieEventNotifierCreate,
    MealieEventNotifierOut,
    MealieEventNotifierUpdate,
    MealieRecipe,
    MealieShoppingListItemCreate,
    MealieShoppingListItemOut,
    MealieShoppingListItemsCollectionOut,
    MealieShoppingListItemUpdateBulk,
    MealieShoppingListOut,
    Pagination,
)

STATUS_CODES_TO_RETRY = [429, 500]


class Routes:
    FOODS = "/api/foods"

    GROUPS_EVENTS_NOTIFICATIONS = "/api/groups/events/notifications"
    GROUPS_EVENTS_NOTIFICATIONS_NOTIFICATION_ID = (  # NOQA: E731
        lambda notification_id: f"{Routes.GROUPS_EVENTS_NOTIFICATIONS}/{notification_id}"
    )

    GROUPS_LABELS = "/api/groups/labels"

    GROUPS_SHOPPING_LISTS = "/api/groups/shopping/lists"
    GROUPS_SHOPPING_LISTS_SHOPPING_LIST_ID = lambda list_id: f"{Routes.GROUPS_SHOPPING_LISTS}/{list_id}"  # NOQA: E731
    GROUPS_SHOPPING_ITEMS = "/api/groups/shopping/items"
    GROUPS_SHOPPING_ITEMS_CREATE_BULK = "/api/groups/shopping/items/create-bulk"

    RECIPES = "/api/recipes"

    USERS_SELF = "/api/users/self"
    USERS_API_TOKENS = "/api/users/api-tokens"
    USERS_API_TOKENS_TOKEN_ID = lambda token_id: f"{Routes.USERS_API_TOKENS}/{token_id}"  # NOQA: E731


class MealieBaseClient:
    """
    Low-level client for interacting with the Mealie API

    Don't use this directly, use the MealieClient instead
    """

    def __init__(
        self,
        base_url: str,
        auth_token: str,
        timeout: int = 30,
        rate_limit_throttle: int = 5,
        max_attempts: int = 3,
    ) -> None:
        if not base_url:
            raise ValueError("base_url must not be empty")

        if base_url[-1] != "/":
            base_url += "/"

        if "http" not in base_url:
            base_url = "https://" + base_url

        self.base_url = base_url
        self._client = self._get_client()
        self._client.headers.update(
            {
                "content-type": "application/json",
                "Authorization": f"Bearer {auth_token}",
            }
        )

        self.timeout = timeout
        self.rate_limit_throttle = rate_limit_throttle
        self.max_attempts = max_attempts

    @classmethod
    def _get_client(cls, *args, **kwargs):
        return requests.session(*args, **kwargs)

    def _request(
        self,
        method: str,
        endpoint: str,
        headers: dict | None = None,
        params: dict | None = None,
        payload: list | dict | None = None,
    ) -> Response:
        if not endpoint or endpoint == "/":
            raise ValueError("endpoint must not be empty")

        if endpoint[0] == "/":
            endpoint = endpoint[1:]

        url = self.base_url + endpoint

        attempt = 0
        while True:
            attempt += 1
            try:
                r = self._client.request(
                    method.upper(),
                    url,
                    headers=headers,
                    params=params,
                    json=payload,
                    timeout=self.timeout,
                )
                r.raise_for_status()
                return r

            except HTTPError as e:
                if attempt >= self.max_attempts:
                    raise

                response: Response = e.response
                if response.status_code not in STATUS_CODES_TO_RETRY:
                    raise

                time.sleep(self.rate_limit_throttle)
                continue

    def get(self, endpoint: str, headers: dict | None = None, params: dict | None = None) -> Response:
        return self._request("GET", endpoint, headers, params)

    def get_all(self, endpoint: str, headers: dict | None = None, params: dict | None = None) -> Iterable[dict]:
        """Paginate through all records, making additional API calls as needed"""

        if params is None:
            params = {}

        has_more = True
        params["page"] = 0
        records = deque[dict]()

        # paginate data until we run out
        while True:
            if not records and has_more:
                params["page"] += 1
                response = self.get(endpoint, headers, params)
                pagination = Pagination.parse_response(response)

                if not pagination.next:
                    has_more = False

                records.extend(pagination.items)

            if not records:
                break

            yield records.pop()

    def head(self, endpoint: str, headers: dict | None = None, params: dict | None = None) -> Response:
        return self._request("HEAD", endpoint, headers, params)

    def patch(
        self,
        endpoint: str,
        payload: list | dict | None = None,
        headers: dict | None = None,
        params: dict | None = None,
    ) -> Response:
        return self._request("PATCH", endpoint, headers, params, payload)

    def post(
        self,
        endpoint: str,
        payload: list | dict | None = None,
        headers: dict | None = None,
        params: dict | None = None,
    ) -> Response:
        return self._request("POST", endpoint, headers, params, payload)

    def put(
        self,
        endpoint: str,
        payload: list | dict | None = None,
        headers: dict | None = None,
        params: dict | None = None,
    ) -> Response:
        return self._request("PUT", endpoint, headers, params, payload)

    def delete(
        self,
        endpoint: str,
        payload: list | dict | None = None,
        headers: dict | None = None,
        params: dict | None = None,
    ) -> Response:
        return self._request("DELETE", endpoint, headers, params, payload)


class MealieClient:
    """Mid-level client for interacting with the Mealie API"""

    def __init__(self, base_url: str, auth_token: str) -> None:
        self.client = MealieBaseClient(base_url, auth_token)

    @property
    def is_valid(self) -> bool:
        """Call the Mealie API and check if the configuration is valid"""

        try:
            self.client.get(Routes.USERS_SELF)
            return True

        except HTTPError:
            return False

    def create_auth_token(self, name: str, integration_id: str | None = None) -> AuthToken:
        response = self.client.post(Routes.USERS_API_TOKENS, payload={"name": name, "integrationId": integration_id})
        return AuthToken.parse_obj(response.json())

    def delete_auth_token(self, token_id: str) -> None:
        self.client.delete(Routes.USERS_API_TOKENS_TOKEN_ID(token_id))

    def create_notifier(self, name: str, apprise_url: str) -> MealieEventNotifierOut:
        payload = MealieEventNotifierCreate(name=name, apprise_url=apprise_url)

        response = self.client.post(
            Routes.GROUPS_EVENTS_NOTIFICATIONS,
            payload=payload.dict(),
        )

        return MealieEventNotifierOut.parse_obj(response.json())

    def update_notifier(self, notifier: MealieEventNotifierUpdate) -> MealieEventNotifierOut:
        response = self.client.put(
            Routes.GROUPS_EVENTS_NOTIFICATIONS_NOTIFICATION_ID(notifier.id),
            payload=notifier.dict(),
        )

        return MealieEventNotifierOut.parse_obj(response.json())

    def delete_notifier(self, notifier_id: str) -> None:
        self.client.delete(Routes.GROUPS_EVENTS_NOTIFICATIONS_NOTIFICATION_ID(notifier_id))

    def get_all_shopping_lists(self) -> Iterable[MealieShoppingListOut]:
        shopping_lists_data = self.client.get_all(Routes.GROUPS_SHOPPING_LISTS)
        for shopping_list_data in shopping_lists_data:
            yield MealieShoppingListOut.parse_obj(shopping_list_data)

    def get_shopping_list(self, shopping_list_id: str):
        response = self.client.get(Routes.GROUPS_SHOPPING_LISTS_SHOPPING_LIST_ID(shopping_list_id))
        return MealieShoppingListOut.parse_response(response)

    def get_all_shopping_list_items(
        self, shopping_list_id: str, include_checked: bool = False, params: dict[str, Any] | None = None
    ) -> Iterable[MealieShoppingListItemOut]:
        query_filter = f"shopping_list_id={shopping_list_id}"
        if not include_checked:
            query_filter += " AND checked=false"

        params = {"queryFilter": query_filter}
        list_items_data = self.client.get_all(Routes.GROUPS_SHOPPING_ITEMS, params=params)
        for list_item_data in list_items_data:
            yield MealieShoppingListItemOut.parse_obj(list_item_data)

    def create_shopping_list_items(
        self, items: list[MealieShoppingListItemCreate]
    ) -> MealieShoppingListItemsCollectionOut:
        response = self.client.post(Routes.GROUPS_SHOPPING_ITEMS_CREATE_BULK, payload=[item.dict() for item in items])
        return MealieShoppingListItemsCollectionOut.parse_response(response)

    def update_shopping_list_items(
        self, items: list[MealieShoppingListItemUpdateBulk]
    ) -> MealieShoppingListItemsCollectionOut:
        response = self.client.put(Routes.GROUPS_SHOPPING_ITEMS, payload=[item.dict() for item in items])
        return MealieShoppingListItemsCollectionOut.parse_response(response)

    def delete_shopping_list_items(self, item_ids: list[str]) -> None:
        response = self.client.delete(Routes.GROUPS_SHOPPING_ITEMS, params={"ids": item_ids})
        response_json: dict[str, Any] = response.json()
        if response_json.get("error"):
            # TODO: make this a custom exception type
            raise Exception("API returned an error when trying to bulk delete items")

    def get_all_recipes(self) -> Iterable[MealieRecipe]:
        recipes_data = self.client.get_all(Routes.RECIPES)
        for recipe_data in recipes_data:
            yield MealieRecipe.parse_obj(recipe_data)

    def get_all_foods(self) -> Iterable[Food]:
        foods_data = self.client.get_all(Routes.FOODS)
        for food_data in foods_data:
            yield Food.parse_obj(food_data)

    def get_all_labels(self) -> Iterable[Label]:
        labels_data = self.client.get_all(Routes.GROUPS_LABELS)
        for label_data in labels_data:
            yield Label.parse_obj(label_data)
