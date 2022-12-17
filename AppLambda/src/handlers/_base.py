from abc import ABC, abstractmethod
from typing import Optional

from ..models.aws import SQSMessage
from ..models.core import ListSyncMap, User
from ..services.mealie import MealieListService


class CannotHandleListMapError(Exception):
    def __init__(self):
        super().__init__("Cannot handle this list map")


class BaseSyncHandler(ABC):
    def __init__(self, user: User, mealie_service: MealieListService):
        self.user = user
        self.mealie_service = mealie_service

    @classmethod
    @abstractmethod
    def can_handle_message(cls, message: SQSMessage) -> bool:
        """parse an SQS message and return whether or not this handler can handle it"""
        pass

    @classmethod
    @abstractmethod
    def can_sync_list_map(self, list_sync_map: ListSyncMap) -> bool:
        """read a list map and return whether or not this handler can use it to sync"""
        pass

    @abstractmethod
    def get_sync_map_from_message(self, message: SQSMessage) -> Optional[ListSyncMap]:
        """read an SQS message and return the appropriate list map, if there is one"""
        pass

    @abstractmethod
    def sync_changes_to_mealie(self, list_sync_map: ListSyncMap):
        """handle sync from this handler's system to Mealie"""
        pass

    @abstractmethod
    def receive_changes_from_mealie(self, list_sync_map: ListSyncMap):
        """receive changes from Mealie and make changes in this handler's system"""
        pass
