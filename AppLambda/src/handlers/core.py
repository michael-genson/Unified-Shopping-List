from typing import Type

from pydantic import ValidationError

from ..models.account_linking import NotLinkedError
from ..models.aws import SQSMessage
from ..models.core import BaseSyncEvent, ListSyncMap, Source, User
from ..models.mealie import MealieSyncEvent
from ..services.mealie import MealieListService
from ._base import BaseSyncHandler
from .alexa import AlexaSyncHandler
from .todoist import TodoistSyncHandler


class SQSSyncMessageHandler:
    registered_handlers: list[Type[BaseSyncHandler]] = [AlexaSyncHandler, TodoistSyncHandler]

    def __init__(self, user: User):
        if not user.is_linked_to_mealie:
            raise NotLinkedError(user.username, "mealie")

        self.user = user
        self.mealie = MealieListService(user)

    def sync_to_external_systems(self, sync_event: BaseSyncEvent, list_sync_map: ListSyncMap):
        """Sync all mealie items to external systems"""

        # handle items in each linked system
        for registered_handler in self.registered_handlers:
            if not registered_handler.can_sync_list_map(list_sync_map):
                continue

            handler = registered_handler(self.user, self.mealie)
            handler.receive_changes_from_mealie(sync_event, list_sync_map)

    def handle_message(self, message: SQSMessage) -> Source | None:
        """
        Parse SQS message and handle its sync event

        Returns the event source only if the message was processed and the handler skips additional events
        """

        try:
            base_sync_event = message.parse_body(BaseSyncEvent)

        except ValidationError:
            raise Exception("Unable to process SQS sync event message. Are you sure this is a sync event?")

        list_sync_map: ListSyncMap | None = None

        # sync to all external systems
        if base_sync_event.source == Source.mealie.value:
            mealie_sync_event = message.parse_body(MealieSyncEvent)
            if mealie_sync_event.shopping_list_id in self.user.list_sync_maps:
                list_sync_map = self.user.list_sync_maps[mealie_sync_event.shopping_list_id]

            else:
                return None

            self.sync_to_external_systems(base_sync_event, list_sync_map)
            return base_sync_event.source  # mealie always skips additional events if a sync is successful

        # sync the event's source system to Mealie
        response: Source | None = None
        for registered_handler in self.registered_handlers:
            if not registered_handler.can_handle_message(message):
                continue

            handler = registered_handler(self.user, self.mealie)
            list_sync_map = handler.get_sync_map_from_message(message)
            if not list_sync_map:
                continue

            handler.sync_changes_to_mealie(message, list_sync_map)
            if handler.suppress_additional_messages:
                response = base_sync_event.source

            break

        if not list_sync_map:
            return None

        # propagate changes made to Mealie to all systems
        self.sync_to_external_systems(base_sync_event, list_sync_map)
        return response
