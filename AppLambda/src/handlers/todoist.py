import logging
from typing import Optional

from pydantic import ValidationError
from todoist_api_python.models import Task

from ..config import TODOIST_MEALIE_LABEL
from ..models.aws import SQSMessage
from ..models.core import BaseSyncEvent, ListSyncMap, Source, User
from ..models.mealie import (
    Label,
    MealieShoppingListItemCreate,
    MealieShoppingListItemExtras,
    MealieShoppingListItemOut,
    MealieShoppingListItemUpdate,
)
from ..models.todoist import TodoistSyncEvent
from ..services.mealie import MealieListService
from ..services.todoist import TodoistTaskService
from ._base import BaseSyncHandler, CannotHandleListMapError


class TodoistSyncHandler(BaseSyncHandler):
    def __init__(
        self,
        user: User,
        mealie_service: MealieListService,
    ):
        super().__init__(user, mealie_service)

        self.todoist_service = TodoistTaskService(user)
        self.extras_key = "todoist_task_id"

    @classmethod
    def can_handle_message(cls, message: SQSMessage):
        try:
            sync_event = message.parse_body(BaseSyncEvent)
            return sync_event.source == Source.todoist.value

        except ValidationError:
            return False

    @classmethod
    def can_sync_list_map(cls, list_sync_map: ListSyncMap):
        return bool(list_sync_map.todoist_project_id)

    def get_sync_map_from_message(self, message: SQSMessage):
        sync_event = message.parse_body(TodoistSyncEvent)
        project_id = sync_event.project_id

        for list_sync_map in self.user.list_sync_maps.values():
            if list_sync_map.todoist_project_id == project_id:
                return list_sync_map

    def get_mealie_item_by_task_id(
        self, mealie_list_id: str, task_id: str
    ) -> Optional[MealieShoppingListItemOut]:
        return self.mealie_service.get_item_by_extra(mealie_list_id, self.extras_key, task_id)

    def get_mealie_label_by_task(self, task: Task) -> Optional[Label]:
        if not task.section_id:
            return None

        if self.todoist_service.is_default_section(task.section_id, task.project_id):
            return None

        section = self.todoist_service.get_section_by_id(task.section_id)
        return self.mealie_service.get_label(section.name)

    def sync_changes_to_mealie(self, list_sync_map: ListSyncMap):
        if not list_sync_map.todoist_project_id:
            raise CannotHandleListMapError()

        mealie_list_id = list_sync_map.mealie_shopping_list_id
        project_id = list_sync_map.todoist_project_id

        for task in self.todoist_service.get_tasks(project_id):
            try:
                # if the item is linked, compare the item label and content
                if mealie_item := self.get_mealie_item_by_task_id(mealie_list_id, task.id):
                    if mealie_item.checked:
                        continue

                    if task.content == mealie_item.display:
                        # compare the Mealie label to the Todoist section
                        mealie_label = self.mealie_service.get_label_from_item(mealie_item)
                        if self.todoist_service.is_task_section(
                            str(mealie_label) if mealie_label else None, task
                        ):
                            continue

                        new_label = self.get_mealie_label_by_task(task)
                        self.mealie_service.update_item(
                            mealie_item.cast(
                                MealieShoppingListItemUpdate,
                                label_id=new_label.id if new_label else None,
                            )
                        )

                        continue

                    else:
                        # the content does not match, and we don't have structured item data
                        # in Todoist, so we need to completely replace the item in Mealie
                        self.mealie_service.delete_item(mealie_item)
                        mealie_item_to_create = MealieShoppingListItemCreate(
                            shopping_list_id=mealie_list_id,
                            note=task.content,
                            quantity=0,
                            extras=MealieShoppingListItemExtras(todoist_task_id=task.id),
                        )

                        label = self.get_mealie_label_by_task(task)
                        if label:
                            mealie_item_to_create.label_id = label.id

                        self.mealie_service.create_item(mealie_item_to_create)

                elif TODOIST_MEALIE_LABEL not in task.labels:
                    # the item is not linked, so create the item in Mealie
                    mealie_item_to_create = MealieShoppingListItemCreate(
                        shopping_list_id=mealie_list_id,
                        note=task.content,
                        quantity=0,
                        extras=MealieShoppingListItemExtras(todoist_task_id=task.id),
                    )

                    label = self.get_mealie_label_by_task(task)
                    if label:
                        mealie_item_to_create.label_id = label.id

                    self.mealie_service.create_item(mealie_item_to_create)

            except Exception as e:
                logging.error("Unhandled exception when trying to sync Todoist item to Mealie")
                logging.error(f"{type(e).__name__}: {e}")
                logging.error(task)

        for mealie_item in self.mealie_service.get_list(mealie_list_id).list_items:
            try:
                if mealie_item.checked:
                    continue

                if not (mealie_item.extras and mealie_item.extras.todoist_task_id):
                    continue

                # check off Mealie item
                if not self.todoist_service.get_task(
                    mealie_item.extras.todoist_task_id, project_id
                ):
                    mealie_item.checked = True
                    mealie_item.extras.todoist_task_id = None
                    self.mealie_service.update_item(mealie_item)

            except Exception as e:
                logging.error("Unhandled exception when trying to sync Todoist item to Mealie")
                logging.error(f"{type(e).__name__}: {e}")
                logging.error(mealie_item)

    def receive_changes_from_mealie(self, list_sync_map: ListSyncMap):
        if not list_sync_map.todoist_project_id:
            raise CannotHandleListMapError()

        mealie_list_id = list_sync_map.mealie_shopping_list_id
        project_id = list_sync_map.todoist_project_id

        for task in self.todoist_service.get_tasks(project_id):
            try:
                # if the item is linked, update the task content
                mealie_item = self.get_mealie_item_by_task_id(mealie_list_id, task.id)
                if mealie_item and not mealie_item.checked:
                    # if the items match, do nothing
                    mealie_label = self.mealie_service.get_label_from_item(mealie_item)
                    if (
                        mealie_item.display == task.content
                        and self.todoist_service.is_task_section(
                            str(mealie_label) if mealie_label else None, task
                        )
                        and TODOIST_MEALIE_LABEL in task.labels
                    ):
                        continue

                    # if the items don't match, update Todoist to match Mealie
                    updated_task = self.todoist_service.update_task(
                        task_id=task.id,
                        project_id=project_id,
                        content=mealie_item.display,
                        section=str(mealie_label) if mealie_label else None,
                        labels=task.labels + [TODOIST_MEALIE_LABEL],
                    )

                    # if the updated task has a new id, write it back to Mealie
                    if updated_task.id != task.id:
                        if not mealie_item.extras:
                            mealie_item.extras = MealieShoppingListItemExtras()

                        mealie_item.extras.todoist_task_id = updated_task.id
                        self.mealie_service.update_item(mealie_item)

                # close Todoist task if it used to be linked to a Mealie item
                elif TODOIST_MEALIE_LABEL in task.labels:
                    self.todoist_service.close_task(task)

            except Exception as e:
                logging.error(
                    "Unhandled exception when trying to receive Mealie change in Todoist"
                )
                logging.error(f"{type(e).__name__}: {e}")
                logging.error(task)

        for mealie_item in self.mealie_service.get_list(mealie_list_id).list_items:
            try:
                if mealie_item.checked:
                    continue

                if mealie_item.extras and mealie_item.extras.todoist_task_id:
                    continue

                # create new Todoist task
                mealie_label = self.mealie_service.get_label_from_item(mealie_item)
                new_task = self.todoist_service.add_task(
                    content=mealie_item.display,
                    project_id=project_id,
                    section=str(mealie_label) if mealie_label else None,
                    labels=[TODOIST_MEALIE_LABEL],
                )

                # write new id back to Mealie
                if not mealie_item.extras:
                    mealie_item.extras = MealieShoppingListItemExtras()

                mealie_item.extras.todoist_task_id = new_task.id
                self.mealie_service.update_item(mealie_item)

            except Exception as e:
                logging.error(
                    "Unhandled exception when trying to receive Mealie change in Todoist"
                )
                logging.error(f"{type(e).__name__}: {e}")
                logging.error(mealie_item)
