from functools import cache
from typing import cast

from fastapi import Depends
from pydantic import ValidationError

from ..clients.alexa import (
    NO_RESPONSE_DATA_EXCEPTION,
    NO_RESPONSE_EXCEPTION,
    ListManagerClient,
)
from ..config import ALEXA_INTERNAL_SOURCE_ID
from ..models.account_linking import NotLinkedError, UserAlexaConfiguration
from ..models.alexa import (
    AlexaListCollectionOut,
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

        self.lists: dict[str, AlexaListOut] = {}
        """map of {list_id: list}"""

    @cache
    def get_all_lists(
        self, source: str = ALEXA_INTERNAL_SOURCE_ID, active_lists_only: bool = True
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

    def get_list(self, alexa_list: AlexaReadList, source: str = ALEXA_INTERNAL_SOURCE_ID) -> AlexaListOut:
        """Fetch a single list from Alexa"""

        if alexa_list.list_id in self.lists:
            return self.lists[alexa_list.list_id]

        request = MessageRequest(operation=Operation.read, object_type=ObjectType.list, object_data=alexa_list.dict())
        message = MessageIn(source=source, requests=[request], send_callback_response=True)

        response = client.call_api(self.user_id, message)
        if not response:
            raise Exception(NO_RESPONSE_EXCEPTION)

        try:
            # since we only sent one request, we can expect exactly one response
            alexa_list = AlexaListOut.parse_obj(response[0])

            self.lists[alexa_list.list_id] = alexa_list
            return alexa_list

        except IndexError:
            raise Exception(NO_RESPONSE_DATA_EXCEPTION)

        except ValidationError:
            raise Exception("Response from Alexa is not a valid list")
