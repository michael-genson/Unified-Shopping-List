import random
from typing import Any, Optional

from AppLambda.src.clients.alexa import ListManagerClient
from AppLambda.src.models.alexa import AlexaListOut, AlexaReadList, Message, MessageRequest, ObjectType, Operation
from tests.utils.generators import random_string


def create_message(
    operation: Operation,
    object_type: ObjectType,
    object_data: Optional[dict[str, Any]] = None,
    send_callback=True,
) -> Message:
    request = MessageRequest(operation=operation, object_type=object_type, object_data=object_data)
    return Message(
        source=random_string(),
        event_id=random_string(),
        requests=[request],
        send_callback_response=send_callback,
    )


def test_alexa_list_manager_client_call_api(
    alexa_client: ListManagerClient, alexa_lists_with_items: list[AlexaListOut]
):
    alexa_list = random.choice(alexa_lists_with_items)
    message = create_message(
        Operation.read,
        object_type=ObjectType.list,
        object_data=AlexaReadList(list_id=alexa_list.list_id, state=alexa_list.state).dict(),
    )
    response = alexa_client.call_api(random_string(), message)

    assert response
    assert len(response) == 1
    list_data = response[0]
    parsed_list = AlexaListOut.parse_obj(list_data)
    assert parsed_list == alexa_list
