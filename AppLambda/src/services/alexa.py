from functools import cache
from typing import cast

from pydantic import ValidationError

from ..clients.alexa import (
    NO_RESPONSE_DATA_EXCEPTION,
    NO_RESPONSE_EXCEPTION,
    ListManagerClient,
)
from ..models.account_linking import NotLinkedError, UserAlexaConfiguration
from ..models.alexa import (
    AlexaReadList,
    AlexaReadListCollection,
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

        self.lists: dict[str, AlexaReadList] = {}
        """map of {list_id: list}"""

    @cache
    def get_all_lists(self, source: str, active_lists_only: bool = True) -> AlexaReadListCollection:
        """Fetch all lists from the user's Alexa account"""

        request = MessageRequest(
            operation=Operation.read_all,
            object_type=ObjectType.list,
        )

        message = MessageIn(
            source=source,
            requests=[request],
            send_callback_response=True,
        )

        response = client.call_api(self.user_id, message)
        if not response:
            raise Exception(NO_RESPONSE_EXCEPTION)

        try:
            # since we only sent one request, we can expect exactly one response
            list_collection = AlexaReadListCollection.parse_obj(response[0])
            if active_lists_only:
                list_collection.lists = [
                    alexa_list for alexa_list in list_collection.lists if alexa_list.state == ListState.active
                ]

            # we don't update self.lists because we don't receive item data from this request
            return list_collection

        except IndexError:
            raise Exception(NO_RESPONSE_DATA_EXCEPTION)

        except ValidationError:
            raise Exception("Response from Alexa is not a valid list collection")
