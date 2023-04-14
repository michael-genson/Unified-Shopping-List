import json
from datetime import datetime
from typing import Optional

from AppLambda.src import config
from AppLambda.src.models.alexa import AlexaListEvent, ObjectType, Operation
from AppLambda.src.models.mealie import MealieEventNotification, MealieEventType
from AppLambda.src.models.todoist import TodoistEventType, TodoistWebhook

from .generators import random_string


def build_mealie_event_notification(
    event_type: MealieEventType, shopping_list_id: str, use_internal_integration_id=False
) -> MealieEventNotification:
    return MealieEventNotification(
        event_id=random_string(),
        timestamp=datetime.now(),
        version="nightly",
        title=random_string(),
        message=random_string(),
        event_type=event_type,
        integration_id=config.MEALIE_INTEGRATION_ID if use_internal_integration_id else random_string(),
        document_data=json.dumps({"shoppingListId": shopping_list_id}),
    )


def build_todoist_webhook(event_type: TodoistEventType, user_id: str, project_id: str) -> TodoistWebhook:
    return TodoistWebhook(
        version=9, event_name=event_type, user_id=user_id, initiator={}, event_data={"project_id": project_id}
    )


def build_alexa_list_event(
    operation: Operation, object_type: ObjectType, list_id: str, list_item_ids: Optional[list[str]] = None
) -> AlexaListEvent:
    if not list_item_ids:
        if object_type is object_type.list_item:
            raise Exception("list item ids must be provided when using the list item object type")
        else:
            list_item_ids = []

    return AlexaListEvent(
        request_id=random_string(),
        timestamp=datetime.now(),
        operation=operation,
        object_type=object_type,
        list_id=list_id,
        list_item_ids=list_item_ids,
    )
