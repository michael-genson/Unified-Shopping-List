import logging
from typing import Optional

from pydantic import ValidationError
from todoist_api_python.models import Task

from .. import config
from ..models.aws import SQSMessage
from ..models.core import BaseSyncEvent, ListSyncMap, Source, User
from ..models.mealie import (
    Label,
    MealieShoppingListItemCreate,
    MealieShoppingListItemExtras,
    MealieShoppingListItemOut,
    MealieShoppingListItemUpdateBulk,
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

    @property
    def suppress_additional_messages(self) -> bool:
        return True

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

    def get_mealie_item_by_task_id(self, mealie_list_id: str, task_id: str) -> Optional[MealieShoppingListItemOut]:
        return self.mealie_service.get_item_by_extra(mealie_list_id, self.extras_key, task_id)

    def get_mealie_label_by_task(self, task: Task) -> Optional[Label]:
        if not task.section_id:
            return None

        if self.todoist_service.is_default_section(task.section_id, task.project_id):
            return None

        section = self.todoist_service.get_section_by_id(task.section_id)
        return self.mealie_service.get_label(section.name)

    def build_task_description_from_mealie_item(self, mealie_item: MealieShoppingListItemOut) -> str:
        # TODO: implement a fetch-recipe-by-id method in Mealie so we don't need to fetch the entire recipe store
        recipe_ids = set(ref.recipe_id for ref in mealie_item.recipe_references)
        recipes = [self.mealie_service.recipe_store.get(recipe_id) for recipe_id in recipe_ids]

        if not recipes:
            return ""

        # [My Recipe](https://url-to-my-recipe.com) | ...
        recipes_string = " | ".join(
            sorted(
                [
                    f"[{recipe}]({self.mealie_service.get_recipe_url(recipe.id)})"
                    for recipe in recipes
                    if recipe and str(recipe)
                ]
            )
        )
        return f"From: {recipes_string}"

    def sync_changes_to_mealie(self, message: SQSMessage, list_sync_map: ListSyncMap):
        if not list_sync_map.todoist_project_id:
            raise CannotHandleListMapError()

        mealie_list_id = list_sync_map.mealie_shopping_list_id
        project_id = list_sync_map.todoist_project_id

        mealie_items_to_create: list[MealieShoppingListItemCreate] = []
        mealie_items_to_update: list[MealieShoppingListItemUpdateBulk] = []
        mealie_items_to_delete: list[MealieShoppingListItemOut] = []
        for task in self.todoist_service.get_tasks(project_id):
            try:
                # if the item is linked, compare the item label and content
                if mealie_item := self.get_mealie_item_by_task_id(mealie_list_id, task.id):
                    if mealie_item.checked:
                        continue

                    if task.content == mealie_item.display:
                        # compare the Mealie label to the Todoist section
                        mealie_label = self.mealie_service.get_label_from_item(mealie_item)
                        if self.todoist_service.is_task_section(str(mealie_label) if mealie_label else None, task):
                            continue

                        new_label = self.get_mealie_label_by_task(task)
                        mealie_items_to_update.append(
                            mealie_item.cast(
                                MealieShoppingListItemUpdateBulk,
                                label_id=new_label.id if new_label else None,
                            )
                        )

                        continue

                    else:
                        # the content does not match, and we don't have structured item data
                        # in Todoist, so we need to completely replace the item in Mealie
                        mealie_items_to_delete.append(mealie_item)
                        mealie_item_to_create = MealieShoppingListItemCreate(
                            shopping_list_id=mealie_list_id,
                            note=task.content,
                            quantity=0,
                            extras=MealieShoppingListItemExtras(todoist_task_id=task.id),
                        )

                        label = self.get_mealie_label_by_task(task)
                        if label:
                            mealie_item_to_create.label_id = label.id

                        mealie_items_to_create.append(mealie_item_to_create)

                elif config.TODOIST_MEALIE_LABEL not in task.labels:
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

                    mealie_items_to_create.append(mealie_item_to_create)

            except Exception as e:
                logging.error("Unhandled exception when trying to sync Todoist item to Mealie")
                logging.error(f"{type(e).__name__}: {e}")
                logging.error(task)

        for mealie_item in self.mealie_service.get_all_list_items(mealie_list_id):
            try:
                if mealie_item.checked:
                    continue

                if not (mealie_item.extras and mealie_item.extras.todoist_task_id):
                    continue

                # check off Mealie item
                if not self.todoist_service.get_task(mealie_item.extras.todoist_task_id, project_id):
                    mealie_item.checked = True
                    mealie_item.extras.todoist_task_id = None
                    mealie_items_to_update.append(mealie_item.cast(MealieShoppingListItemUpdateBulk))

            except Exception as e:
                logging.error("Unhandled exception when trying to sync Todoist item to Mealie")
                logging.error(f"{type(e).__name__}: {e}")
                logging.error(mealie_item)

        try:
            self.mealie_service.bulk_handle_items(
                mealie_items_to_create, mealie_items_to_update, mealie_items_to_delete
            )

        except Exception as e:
            logging.error(f"Unhandled exception when trying to perform bulk CRUD op from Todoist to Mealie")

    def receive_changes_from_mealie(self, sync_event: BaseSyncEvent, list_sync_map: ListSyncMap):
        if not list_sync_map.todoist_project_id:
            raise CannotHandleListMapError()

        mealie_list_id = list_sync_map.mealie_shopping_list_id
        project_id = list_sync_map.todoist_project_id
        mealie_items_to_update: list[MealieShoppingListItemUpdateBulk] = []
        for task in self.todoist_service.get_tasks(project_id):
            try:
                # if the item is linked, update the task content
                mealie_item = self.get_mealie_item_by_task_id(mealie_list_id, task.id)
                if mealie_item and not mealie_item.checked:
                    # if the items match, do nothing
                    mealie_label = self.mealie_service.get_label_from_item(mealie_item)
                    if (
                        mealie_item.display == task.content
                        and self.todoist_service.is_task_section(str(mealie_label) if mealie_label else None, task)
                        and config.TODOIST_MEALIE_LABEL in task.labels
                    ):
                        continue

                    # if the items don't match, update Todoist to match Mealie
                    updated_task = self.todoist_service.update_task(
                        task_id=task.id,
                        project_id=project_id,
                        content=mealie_item.display,
                        section=str(mealie_label) if mealie_label else None,
                        labels=task.labels + [config.TODOIST_MEALIE_LABEL],
                        description=self.build_task_description_from_mealie_item(mealie_item),
                    )

                    # if the updated task has a new id, write it back to Mealie
                    if updated_task.id != task.id:
                        if not mealie_item.extras:
                            mealie_item.extras = MealieShoppingListItemExtras()

                        mealie_item.extras.todoist_task_id = updated_task.id
                        mealie_items_to_update.append(mealie_item.cast(MealieShoppingListItemUpdateBulk))

                # close Todoist task if it used to be linked to a Mealie item
                elif config.TODOIST_MEALIE_LABEL in task.labels:
                    self.todoist_service.close_task(task)

            except Exception as e:
                logging.error("Unhandled exception when trying to receive Mealie change in Todoist")
                logging.error(f"{type(e).__name__}: {e}")
                logging.error(task)

        for mealie_item in self.mealie_service.get_all_list_items(mealie_list_id):
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
                    labels=[config.TODOIST_MEALIE_LABEL],
                    description=self.build_task_description_from_mealie_item(mealie_item),
                )

                # write new id back to Mealie
                if not mealie_item.extras:
                    mealie_item.extras = MealieShoppingListItemExtras()

                mealie_item.extras.todoist_task_id = new_task.id
                mealie_items_to_update.append(mealie_item.cast(MealieShoppingListItemUpdateBulk))

            except Exception as e:
                logging.error("Unhandled exception when trying to receive Mealie change in Todoist")
                logging.error(f"{type(e).__name__}: {e}")
                logging.error(mealie_item)

        try:
            self.mealie_service.update_items(mealie_items_to_update)

        except Exception as e:
            logging.error(f"Unhandled exception when trying to bulk update Mealie items with new Todoist task ids")
