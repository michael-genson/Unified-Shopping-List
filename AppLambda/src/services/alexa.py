from cachetools.func import ttl_cache
from pydantic import ValidationError

from ..clients.alexa import NO_RESPONSE_EXCEPTION, ListManagerBaseClient
from ..models.alexa import (
    AlexaReadListCollection,
    ListState,
    MessageIn,
    ObjectType,
    Operation,
)

client = ListManagerBaseClient()


class AlexaListService:
    @ttl_cache(ttl=60 * 5)
    def get_all_lists(
        self,
        user_id: str,
        source: str,
        active_lists_only: bool = True,
    ) -> AlexaReadListCollection:
        message = MessageIn(
            source=source,
            operation=Operation.read_all,
            object_type=ObjectType.list,
            send_callback_response=True,
        )

        response = client.call_api(user_id, message)
        if not response:
            raise Exception(NO_RESPONSE_EXCEPTION)

        try:
            list_collection = AlexaReadListCollection.parse_obj(response)
            if active_lists_only:
                list_collection.lists = [
                    alexa_list for alexa_list in list_collection.lists if alexa_list.state == ListState.active
                ]

            return list_collection

        except ValidationError:
            raise Exception("Response from Alexa is not a valid list collection")
