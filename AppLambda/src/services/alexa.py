import logging
from copy import deepcopy
from functools import cache
from typing import Any, cast

from pydantic import ValidationError

from ..app import settings
from ..clients.alexa import NO_RESPONSE_DATA_EXCEPTION, NO_RESPONSE_EXCEPTION, ListManagerClient
from ..models.account_linking import NotLinkedError, UserAlexaConfiguration
from ..models.alexa import (
    AlexaListCollectionOut,
    AlexaListItemCollectionOut,
    AlexaListItemCreate,
    AlexaListItemCreateIn,
    AlexaListItemOut,
    AlexaListItemUpdate,
    AlexaListItemUpdateBulkIn,
    AlexaListOut,
    AlexaReadList,
    ListState,
    MessageIn,
    MessageRequest,
    ObjectType,
    Operation,
)
from ..models.core import User

client = ListManagerClient()


class AlexaListService:
    def __init__(self, user: User) -> None:
        if not user.is_linked_to_alexa:
            raise NotLinkedError(user.username, "alexa")

        self.user_id: str = cast(str, user.alexa_user_id)
        self.config = cast(UserAlexaConfiguration, user.configuration.alexa)

        self._list_cache: dict[str, AlexaListOut] = {}
        """map of {list_id: list}"""

    def _clear_cache(self) -> None:
        self._list_cache.clear()
        self.get_all_lists.cache_clear()

    @cache
    def get_all_lists(
        self, source: str = settings.alexa_internal_source_id, active_lists_only: bool = True
    ) -> AlexaListCollectionOut:
        """Fetch all lists from Alexa"""

        request = MessageRequest(operation=Operation.read_all, object_type=ObjectType.list)
        message = MessageIn(source=source, requests=[request], send_callback_response=True)

        response = client.call_api(self.user_id, message)
        if not response:
            raise Exception(NO_RESPONSE_EXCEPTION)

        try:
            # since we only sent one request, we can expect exactly one response
            list_collection = AlexaListCollectionOut.parse_obj(response[0])
            if active_lists_only:
                list_collection.lists = [
                    alexa_list for alexa_list in list_collection.lists if alexa_list.state == ListState.active.value
                ]

            # we don't update self.lists because we don't receive item data from this request
            return list_collection

        except IndexError:
            raise Exception(NO_RESPONSE_DATA_EXCEPTION)

        except ValidationError:
            raise Exception("Response from Alexa is not a valid list collection")

    def _get_list(
        self, list_id: str, state: ListState = ListState.active, source: str = settings.alexa_internal_source_id
    ) -> AlexaListOut:
        """
        Fetch a single list from Alexa or from local cache

        Mutations to the list or to any items in the list will
        modify the local cache

        For a safe list, see `get_list`
        """

        if list_id in self._list_cache:
            return self._list_cache[list_id]

        request = MessageRequest(
            operation=Operation.read,
            object_type=ObjectType.list,
            object_data=AlexaReadList(list_id=list_id, state=state),
        )
        message = MessageIn(source=source, requests=[request], send_callback_response=True)

        response = client.call_api(self.user_id, message)
        if not response:
            raise Exception(NO_RESPONSE_EXCEPTION)

        try:
            # since we only sent one request, we can expect exactly one response
            alexa_list = AlexaListOut.parse_obj(response[0])

            self._list_cache[alexa_list.list_id] = alexa_list
            return alexa_list

        except IndexError:
            raise Exception(NO_RESPONSE_DATA_EXCEPTION)

        except ValidationError as e:
            logging.error("Response from Alexa is not a valid list")
            logging.error(e)
            logging.error(response)
            raise Exception("Response from Alexa is not a valid list")

    def get_list(
        self, list_id: str, state: ListState = ListState.active, source: str = settings.alexa_internal_source_id
    ) -> AlexaListOut:
        """Fetch a single list from Alexa or from local cache that can be safely mutated"""
        return deepcopy(self._get_list(list_id, state, source))

    def get_list_item(
        self, list_id: str, item_id: str, source: str = settings.alexa_internal_source_id
    ) -> AlexaListItemOut | None:
        """Fetch a single list item from Alexa that can be safely mutated"""

        alexa_list = self._get_list(list_id, source=source)
        for list_item in alexa_list.items or []:
            if list_item.id == item_id:
                return deepcopy(list_item)

        return None

    def create_list_items(
        self, list_id: str, items: list[AlexaListItemCreateIn], source: str = settings.alexa_internal_source_id
    ) -> AlexaListItemCollectionOut:
        """Create one or more items in Alexa. Items order is preserved"""

        if not items:
            return AlexaListItemCollectionOut(list_id=list_id, list_items=[])

        alexa_list = self._get_list(list_id, source=source)
        requests = [
            MessageRequest(
                operation=Operation.create,
                object_type=ObjectType.list_item,
                object_data=item.cast(AlexaListItemCreate, list_id=list_id).dict(),
                metadata={"index": i},
            )
            for i, item in enumerate(items)
        ]

        message = MessageIn(source=source, requests=requests, send_callback_response=True)
        response = client.call_api(self.user_id, message)
        if not response:
            raise Exception(NO_RESPONSE_EXCEPTION)

        try:
            # use metadata to preserve order
            new_items_map: dict[int, AlexaListItemOut] = {}
            for data in response:
                metadata: dict[str, Any] = data["metadata"]
                new_items_map[metadata["index"]] = AlexaListItemOut.parse_obj(data)

            # build a list of values sorted by the metadata index
            new_items = list(dict(sorted(new_items_map.items())).values())

        except ValidationError:
            raise Exception("Response from Alexa is not a valid list of items")

        # add items to cached list
        if alexa_list.items is None:
            alexa_list.items = new_items

        else:
            alexa_list.items.extend(new_items)

        return AlexaListItemCollectionOut(list_id=list_id, list_items=deepcopy(new_items))

    def update_list_items(
        self, list_id: str, items: list[AlexaListItemUpdateBulkIn], source: str = settings.alexa_internal_source_id
    ) -> AlexaListItemCollectionOut:
        """Update one or more items in Alexa"""

        alexa_list = self._get_list(list_id, source=source)

        requests: list[MessageRequest] = []
        updated_items: list[AlexaListItemOut] = []
        for item in items:
            for current_item in alexa_list.items or []:
                if item.id != current_item.id:
                    continue

                # update the item in place
                current_item.merge(item)
                updated_items.append(current_item)

                requests.append(
                    MessageRequest(
                        operation=Operation.update,
                        object_type=ObjectType.list_item,
                        object_data=current_item.cast(
                            AlexaListItemUpdate, list_id=list_id, item_id=current_item.id
                        ).dict(),
                    )
                )

                break

        if not requests:
            return AlexaListItemCollectionOut(list_id=list_id, list_items=[])

        message = MessageIn(source=source, requests=requests, send_callback_response=True)
        client.call_api(self.user_id, message)

        # we need to increment the cached version number before returning the updated items
        # the Alexa API does this for us server-side
        for updated_item in updated_items:
            updated_item.version += 1

        return AlexaListItemCollectionOut(list_id=list_id, list_items=deepcopy(updated_items))
