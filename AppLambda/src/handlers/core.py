from typing import Optional

from pydantic import ValidationError

from ..models.account_linking import NotLinkedError
from ..models.aws import SQSMessage
from ..models.core import BaseSyncEvent, ListSyncMap, Source, User
from ..models.mealie import MealieSyncEvent
from ..services.mealie import MealieListService
from .todoist import TodoistSyncHandler


class SQSSyncMessageHandler:
    registered_handlers = [TodoistSyncHandler]

    def __init__(self, user: User):
        if not user.is_linked_to_mealie:
            raise NotLinkedError(user.username, "mealie")

        self.user = user
        self.mealie = MealieListService(user)

    def sync_to_external_systems(self, list_sync_map: ListSyncMap):
        """Sync all mealie items to external systems"""

        # handle items in each linked system
        for registered_handler in self.registered_handlers:
            if not registered_handler.can_sync_list_map(list_sync_map):
                continue

            handler = registered_handler(self.user, self.mealie)
            handler.receive_changes_from_mealie(list_sync_map)

        # delete checked items from Mealie
        # TODO: submit PR to Mealie to allow only querying/pulling unchecked items so we don't have to do this
        recipe_ref_ids_to_keep = set()
        shopping_list = self.mealie.get_list(list_sync_map.mealie_shopping_list_id)
        for list_item in shopping_list.list_items:
            if not list_item.checked and list_item.recipe_references:
                recipe_ref_ids_to_keep.update([ref.recipe_id for ref in list_item.recipe_references])

            if list_item.checked:
                self.mealie.delete_item(list_item)

        # delete empty recipe refs from Mealie
        # we wrap this in a blanket try-except block because the endpoint just changed (https://github.com/hay-kot/mealie/pull/1954)
        # TODO: submit PR to Mealie so this is done automatically when items are checked off or deleted
        try:
            for recipe_ref in shopping_list.recipe_references:
                if recipe_ref.recipe_id not in recipe_ref_ids_to_keep:
                    self.mealie.remove_recipe_ingredients_from_list(shopping_list, recipe_ref.recipe_id)

        except Exception:
            pass

    def handle_message(self, message: SQSMessage) -> Optional[Source]:
        """
        Parse SQS message and handle its sync event

        Returns the event source only if the message was processed and the handler skips additional events
        """

        try:
            base_sync_event = message.parse_body(BaseSyncEvent)

        except ValidationError:
            raise Exception("Unable to process SQS sync event message. Are you sure this is a sync event?")

        list_sync_map: Optional[ListSyncMap] = None

        # sync to all external systems
        if base_sync_event.source == Source.mealie.value:
            mealie_sync_event = message.parse_body(MealieSyncEvent)
            if mealie_sync_event.shopping_list_id in self.user.list_sync_maps:
                list_sync_map = self.user.list_sync_maps[mealie_sync_event.shopping_list_id]

            else:
                return None

            self.sync_to_external_systems(list_sync_map)
            return base_sync_event.source  # mealie always skips additional events if a sync is successful

        # sync the event's source system to Mealie
        response: Optional[Source] = None
        for registered_handler in self.registered_handlers:
            if not registered_handler.can_handle_message(message):
                continue

            handler = registered_handler(self.user, self.mealie)
            list_sync_map = handler.get_sync_map_from_message(message)
            if not list_sync_map:
                continue

            handler.sync_changes_to_mealie(list_sync_map)
            if handler.suppress_additional_messages:
                response = base_sync_event.source

            break

        if not list_sync_map:
            return None

        # propagate changes made to Mealie to all systems
        self.sync_to_external_systems(list_sync_map)
        return response
