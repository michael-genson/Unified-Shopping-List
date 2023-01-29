import contextlib
import logging
from typing import Optional

from pydantic import ValidationError
from pytz import UTC

from ..models.alexa import (
    AlexaListItemCreateIn,
    AlexaListItemOut,
    AlexaListItemUpdateBulkIn,
    AlexaSyncEvent,
    ListItemState,
    Operation,
)
from ..models.aws import SQSMessage
from ..models.core import BaseSyncEvent, ListSyncMap, Source, User
from ..models.mealie import (
    MealieShoppingListItemCreate,
    MealieShoppingListItemExtras,
    MealieShoppingListItemOut,
    MealieShoppingListItemUpdateBulk,
)
from ..services.alexa import AlexaListService
from ..services.mealie import MealieListService
from ._base import BaseSyncHandler, CannotHandleListMapError


class AlexaSyncHandler(BaseSyncHandler):
    def __init__(
        self,
        user: User,
        mealie_service: MealieListService,
    ):
        super().__init__(user, mealie_service)

        self.alexa_service = AlexaListService(user)
        self.extras_item_id_key = "alexa_item_id"
        self.extras_version_key = "alexa_item_version"

    @property
    def suppress_additional_messages(self) -> bool:
        return False

    @classmethod
    def can_handle_message(cls, message: SQSMessage):
        try:
            sync_event = message.parse_body(BaseSyncEvent)
            return sync_event.source == Source.alexa.value

        except ValidationError:
            return False

    @classmethod
    def can_sync_list_map(cls, list_sync_map: ListSyncMap):
        return bool(list_sync_map.alexa_list_id)

    def get_sync_map_from_message(self, message: SQSMessage):
        sync_event = message.parse_body(AlexaSyncEvent)
        list_id = sync_event.list_event.list_id

        for list_sync_map in self.user.list_sync_maps.values():
            if list_sync_map.alexa_list_id == list_id:
                return list_sync_map

    def get_mealie_item_by_item_id(self, mealie_list_id: str, item_id: str) -> Optional[MealieShoppingListItemOut]:
        return self.mealie_service.get_item_by_extra(mealie_list_id, self.extras_item_id_key, item_id)

    def get_mealie_item_version_number(self, mealie_item: MealieShoppingListItemOut) -> int:
        """
        read the mealie item and get its alexa item version

        returns 0 if there is no version information
        """

        if not (mealie_item.extras and mealie_item.extras.alexa_item_version):
            return 0

        if not mealie_item.extras.alexa_item_version.isnumeric():
            return 0

        return int(mealie_item.extras.alexa_item_version)

    def can_update_mealie_item(self, mealie_item: MealieShoppingListItemOut, alexa_item: AlexaListItemOut):
        """compare the alexa item versions and return if the item should be updated in Mealie"""

        mealie_item_version = self.get_mealie_item_version_number(mealie_item)
        return mealie_item_version < alexa_item.version

    def can_update_alexa_item(self, mealie_item: MealieShoppingListItemOut, alexa_item: AlexaListItemOut):
        """
        compare the alexa item versions and return if the item should be updated in Alexa

        should only be used for value updates, not whether or not an item can be checked off
        """

        return not self.can_update_mealie_item(mealie_item, alexa_item)

    def can_check_off_alexa_item(self, sync_event: BaseSyncEvent, alexa_item: AlexaListItemOut):
        """
        compare the timestamps of the sync event and the Alexa item and return if the Alexa item can be checked off

        should only be used as a fallback if we don't know if the Alexa item has synced over to Mealie or not
        TODO: find a more deterministic way to handle these scenarios
        """

        sync_event_timestamp = sync_event.timestamp
        alexa_create_timestamp = alexa_item.created_time

        # some timestamps are missing tzinfo, so we assume it's UTC
        with contextlib.suppress(ValueError):
            sync_event_timestamp = UTC.localize(sync_event_timestamp)

        with contextlib.suppress(ValueError):
            alexa_create_timestamp = UTC.localize(alexa_create_timestamp)

        return sync_event_timestamp >= alexa_create_timestamp

    def sync_changes_to_mealie(self, message: SQSMessage, list_sync_map: ListSyncMap):
        sync_event = message.parse_body(AlexaSyncEvent)
        list_event = sync_event.list_event
        if not list_event.list_item_ids:
            return

        if not list_sync_map.alexa_list_id:
            raise CannotHandleListMapError()

        mealie_list_id = list_sync_map.mealie_shopping_list_id
        alexa_list_id = list_sync_map.alexa_list_id
        alexa_item_ids = list_event.list_item_ids

        mealie_items_to_create: list[MealieShoppingListItemCreate] = []
        mealie_items_to_update: list[MealieShoppingListItemUpdateBulk] = []
        mealie_items_to_delete: list[MealieShoppingListItemOut] = []
        for alexa_item_id in alexa_item_ids:
            try:
                mealie_item = self.get_mealie_item_by_item_id(mealie_list_id, alexa_item_id)
                if list_event.operation == Operation.delete.value:
                    if not mealie_item:
                        continue

                    mealie_item.checked = True
                    if mealie_item.extras:
                        mealie_item.extras.alexa_item_id = None
                        mealie_item.extras.alexa_item_version = None

                    mealie_items_to_update.append(mealie_item.cast(MealieShoppingListItemUpdateBulk))
                    continue

                elif list_event.operation == Operation.create.value:
                    if mealie_item:
                        continue

                    alexa_item = self.alexa_service.get_list_item(alexa_list_id, alexa_item_id)
                    if not alexa_item or alexa_item.status == ListItemState.completed:
                        continue

                    mealie_items_to_create.append(
                        MealieShoppingListItemCreate(
                            shopping_list_id=mealie_list_id,
                            note=alexa_item.value,
                            quantity=0,
                            extras=MealieShoppingListItemExtras(
                                alexa_item_id=alexa_item_id, alexa_item_version=str(alexa_item.version)
                            ),
                        )
                    )

                elif list_event.operation == Operation.update.value:
                    if not mealie_item:
                        continue

                    alexa_item = self.alexa_service.get_list_item(alexa_list_id, alexa_item_id)
                    if not alexa_item or alexa_item.status == ListItemState.completed:
                        mealie_item.checked = True
                        if mealie_item.extras:
                            mealie_item.extras.alexa_item_id = None
                            mealie_item.extras.alexa_item_version = None

                        mealie_items_to_update.append(mealie_item.cast(MealieShoppingListItemUpdateBulk))
                        continue

                    if not self.can_update_mealie_item(mealie_item, alexa_item):
                        continue

                    if alexa_item.value != mealie_item.display:
                        # the content does not match, and we don't have structured item data
                        # in Alexa, so we need to completely replace the item in Mealie
                        mealie_items_to_delete.append(mealie_item)
                        mealie_items_to_create.append(
                            MealieShoppingListItemCreate(
                                shopping_list_id=mealie_list_id,
                                note=alexa_item.value,
                                quantity=0,
                                extras=MealieShoppingListItemExtras(
                                    alexa_item_id=alexa_item.id, alexa_item_version=str(alexa_item.version)
                                ),
                            )
                        )

                        continue

                    # compare item state
                    mealie_item_version = self.get_mealie_item_version_number(mealie_item)
                    if (not mealie_item.checked) and alexa_item.version == mealie_item_version:
                        continue

                    mealie_item.checked = False
                    if not mealie_item.extras:
                        mealie_item.extras = MealieShoppingListItemExtras(
                            alexa_item_id=alexa_item.id, alexa_item_version=str(alexa_item.version)
                        )

                    else:
                        mealie_item.extras.alexa_item_version = str(alexa_item.version)

                    mealie_items_to_update.append(mealie_item.cast(MealieShoppingListItemUpdateBulk))

            except Exception as e:
                logging.error(f"Unhandled exception when trying to {list_event.operation.value} Alexa item in Mealie")
                logging.error(f"{type(e).__name__}: {e}")
                logging.error(alexa_item_id)

        try:
            self.mealie_service.bulk_handle_items(
                mealie_items_to_create, mealie_items_to_update, mealie_items_to_delete
            )

        except Exception as e:
            logging.error(f"Unhandled exception when trying to perform bulk CRUD op from Alexa to Mealie")

    def receive_changes_from_mealie(self, sync_event: BaseSyncEvent, list_sync_map: ListSyncMap):
        if not list_sync_map.alexa_list_id:
            raise CannotHandleListMapError()

        mealie_list_id = list_sync_map.mealie_shopping_list_id
        alexa_list_id = list_sync_map.alexa_list_id

        alexa_items_to_create: list[AlexaListItemCreateIn] = []
        alexa_items_to_update: list[AlexaListItemUpdateBulkIn] = []
        mealie_items_to_callback: list[MealieShoppingListItemOut] = []
        mealie_items_to_update: list[MealieShoppingListItemUpdateBulk] = []
        for alexa_item in self.alexa_service.get_list(alexa_list_id).items or []:
            mealie_item = self.get_mealie_item_by_item_id(mealie_list_id, alexa_item.id)

            # if the Mealie item is checked or non-existent, check off Alexa item
            # TODO: make Mealie retain deleted items for a while, or capture delete events directly so we don't have to rely on timestamps
            if (mealie_item and mealie_item.checked) or (
                (not mealie_item) and self.can_check_off_alexa_item(sync_event, alexa_item)
            ):
                alexa_item.status = ListItemState.completed
                alexa_items_to_update.append(alexa_item.cast(AlexaListItemUpdateBulkIn))
                continue

            if not mealie_item:
                continue

            # the item is linked, so check if the item content matches
            if mealie_item.display == alexa_item.value:
                continue

            if not self.can_update_alexa_item(mealie_item, alexa_item):
                continue

            alexa_item.value = mealie_item.display
            alexa_items_to_update.append(alexa_item.cast(AlexaListItemUpdateBulkIn))
            mealie_items_to_callback.append(mealie_item)

        for mealie_item in self.mealie_service.get_list(mealie_list_id).list_items:
            if mealie_item.checked:
                continue

            if mealie_item.extras and mealie_item.extras.alexa_item_id:
                continue

            alexa_items_to_create.append(AlexaListItemCreateIn(value=mealie_item.display))
            mealie_items_to_callback.append(mealie_item)

        try:
            new_alexa_items = self.alexa_service.create_list_items(alexa_list_id, alexa_items_to_create)
            updated_alexa_items = self.alexa_service.update_list_items(alexa_list_id, alexa_items_to_update)

            alexa_items = new_alexa_items.list_items + updated_alexa_items.list_items
            for mealie_item, alexa_item in zip(mealie_items_to_callback, alexa_items):
                try:
                    if not mealie_item.extras:
                        mealie_item.extras = MealieShoppingListItemExtras()

                    mealie_item.extras.alexa_item_id = alexa_item.id
                    mealie_item.extras.alexa_item_version = str(alexa_item.version)
                    mealie_items_to_update.append(mealie_item.cast(MealieShoppingListItemUpdateBulk))

                except Exception as e:
                    logging.error("Unhandled exception when trying to write Alexa changes back to Mealie")
                    logging.error(f"{type(e).__name__}: {e}")
                    logging.error(mealie_item)

        except Exception as e:
            logging.error("Unhandled exception when trying to bulk create/update Mealie items in Alexa")
            logging.error(f"{type(e).__name__}: {e}")
            logging.error(f"create: {alexa_items_to_create}")
            logging.error(f"update: {alexa_items_to_update}")

        try:
            self.mealie_service.update_items(mealie_items_to_update)

        except Exception as e:
            logging.error(f"Unhandled exception when trying to bulk update Mealie items with new Alexa ids")
