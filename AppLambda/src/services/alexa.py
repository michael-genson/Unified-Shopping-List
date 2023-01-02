from cachetools.func import ttl_cache
from pydantic import ValidationError

from ..clients.alexa import (
    NO_RESPONSE_DATA_EXCEPTION,
    NO_RESPONSE_EXCEPTION,
    ListManagerClient,
)
from ..models.alexa import (
    AlexaReadListCollection,
    ListState,
    MessageIn,
    MessageRequest,
    ObjectType,
    Operation,
)

client = ListManagerClient()


class AlexaListService:
    @ttl_cache(ttl=60 * 5)
    def get_all_lists(
        self,
        user_id: str,
        source: str,
        active_lists_only: bool = True,
    ) -> AlexaReadListCollection:
        request = MessageRequest(
            operation=Operation.read_all,
            object_type=ObjectType.list,
        )

        message = MessageIn(
            source=source,
            requests=[request],
            send_callback_response=True,
        )

        response = client.call_api(user_id, message)
        if not response:
            raise Exception(NO_RESPONSE_EXCEPTION)

        try:
            # since we only sent one request, we can expect exactly one response
            list_collection = AlexaReadListCollection.parse_obj(response[0])
            if active_lists_only:
                list_collection.lists = [
                    alexa_list for alexa_list in list_collection.lists if alexa_list.state == ListState.active
                ]

            return list_collection

        except IndexError:
            raise Exception(NO_RESPONSE_DATA_EXCEPTION)

        except ValidationError:
            raise Exception("Response from Alexa is not a valid list collection")
