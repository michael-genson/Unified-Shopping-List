import time
from collections import deque
from functools import cached_property
from typing import Iterable, Optional

import requests
from requests import HTTPError, Response

from ..models.mealie import (
    AuthToken,
    Food,
    Label,
    MealieEventNotifierCreate,
    MealieEventNotifierOut,
    MealieEventNotifierUpdate,
    MealieShoppingListItemCreate,
    MealieShoppingListItemOut,
    MealieShoppingListItemUpdate,
    MealieShoppingListOut,
    Pagination,
)

STATUS_CODES_TO_RETRY = [429, 500]


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
        self._client = requests.session()
        self._client.headers.update(
            {
                "content-type": "application/json",
                "Authorization": f"Bearer {auth_token}",
            }
        )

        self.timeout = timeout
        self.rate_limit_throttle = rate_limit_throttle
        self.max_attempts = max_attempts

    def _request(
        self,
        method: str,
        endpoint: str,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        payload: Optional[dict] = None,
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

    def get(
        self, endpoint: str, headers: Optional[dict] = None, params: Optional[dict] = None
    ) -> Response:
        return self._request("GET", endpoint, headers, params)

    def get_all(
        self, endpoint: str, headers: Optional[dict] = None, params: Optional[dict] = None
    ) -> Iterable[dict]:
        """Paginate through all records, making additional API calls as needed"""

        if params is None:
            params = {}

        has_more = True
        params["page"] = -1
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

    def head(
        self, endpoint: str, headers: Optional[dict] = None, params: Optional[dict] = None
    ) -> Response:
        return self._request("HEAD", endpoint, headers, params)

    def patch(
        self,
        endpoint: str,
        payload: Optional[dict] = None,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Response:
        return self._request("PATCH", endpoint, headers, params, payload)

    def post(
        self,
        endpoint: str,
        payload: Optional[dict] = None,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Response:
        return self._request("POST", endpoint, headers, params, payload)

    def put(
        self,
        endpoint: str,
        payload: Optional[dict] = None,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Response:
        return self._request("PUT", endpoint, headers, params, payload)

    def delete(
        self,
        endpoint: str,
        payload: Optional[dict] = None,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
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
            self.client.get("/api/users/self")
            return True

        except HTTPError:
            return False

    @cached_property
    def food_store(self) -> dict[str, Food]:
        """Dictionary of { food.name.lower(): foods }"""

        return {food.name.lower(): food for food in self.get_all_foods()}

    def create_auth_token(self, name: str, integration_id: Optional[str] = None) -> AuthToken:
        response = self.client.post(
            "/api/users/api-tokens", payload={"name": name, "integrationId": integration_id}
        )
        return AuthToken.parse_obj(response.json())

    def delete_auth_token(self, token_id: str) -> None:
        self.client.delete(f"/api/users/api-tokens/{token_id}")

    def create_notifier(self, name: str, apprise_url: str) -> MealieEventNotifierOut:
        payload = MealieEventNotifierCreate(name=name, apprise_url=apprise_url)

        response = self.client.post(
            "/api/groups/events/notifications",
            payload=payload.dict(),
        )

        return MealieEventNotifierOut.parse_obj(response.json())

    def update_notifier(self, notifier: MealieEventNotifierUpdate) -> MealieEventNotifierOut:
        response = self.client.put(
            f"/api/groups/events/notifications/{notifier.id}",
            payload=notifier.dict(),
        )

        return MealieEventNotifierOut.parse_obj(response.json())

    def delete_notifier(self, notifier_id: str) -> None:
        self.client.delete(f"/api/groups/events/notifications/{notifier_id}")

    def get_all_shopping_lists(self) -> Iterable[MealieShoppingListOut]:
        shopping_lists_data = self.client.get_all("/api/groups/shopping/lists")
        for shopping_list_data in shopping_lists_data:
            yield MealieShoppingListOut.parse_obj(shopping_list_data)

    def get_shopping_list(self, shopping_list_id: str):
        response = self.client.get(f"/api/groups/shopping/lists/{shopping_list_id}")
        return MealieShoppingListOut.parse_response(response)

    def create_shopping_list_item(
        self, item: MealieShoppingListItemCreate
    ) -> MealieShoppingListItemOut:
        response = self.client.post("/api/groups/shopping/items", payload=item.dict())
        return MealieShoppingListItemOut.parse_response(response)

    def update_shopping_list_item(self, item: MealieShoppingListItemUpdate):
        response = self.client.put(f"/api/groups/shopping/items/{item.id}", payload=item.dict())
        return MealieShoppingListItemOut.parse_response(response)

    def delete_shopping_list_item(self, item_id: str) -> MealieShoppingListItemOut:
        response = self.client.delete(f"/api/groups/shopping/items/{item_id}")
        return MealieShoppingListItemOut.parse_response(response)

    def get_all_foods(self) -> Iterable[Food]:
        foods_data = self.client.get_all("/api/foods")
        for food_data in foods_data:
            yield Food.parse_obj(food_data)

    def get_all_labels(self) -> Iterable[Label]:
        labels_data = self.client.get_all("/api/groups/labels")
        for label_data in labels_data:
            yield Label.parse_obj(label_data)
