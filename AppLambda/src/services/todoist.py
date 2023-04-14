from copy import deepcopy
from functools import cache
from typing import Optional, cast

from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Section, Task

from ..models.account_linking import NotLinkedError, UserTodoistConfiguration
from ..models.core import User


class TodoistTaskService:
    def __init__(self, user: User) -> None:
        if not user.is_linked_to_todoist:
            raise NotLinkedError(user.username, "todoist")

        self.config = cast(UserTodoistConfiguration, user.configuration.todoist)
        self._client = self._get_client(self.config.access_token)

        self.project_tasks: dict[str, list[Task]] = {}
        """map of {project_id: tasks}"""

    @classmethod
    def _get_client(cls, token: str) -> TodoistAPI:
        return TodoistAPI(token)

    def get_section_by_id(self, section_id: str) -> Section:
        return self._client.get_section(section_id)

    @cache
    def get_section(self, section: str, project_id: str) -> Section:
        """Gets an existing section by name, or creates a new one if one doesn't already exist"""

        user_section = section.strip().lower()
        api_sections = self._client.get_sections(project_id=project_id)
        for api_section in api_sections:
            if api_section.name.strip().lower() == user_section:
                return api_section

        return self._client.add_section(section, project_id)

    def is_default_section(self, section_id: str, project_id: str) -> bool:
        default_section = self.get_section(self.config.default_section_name, project_id)
        return section_id == default_section.id

    def is_task_section(self, section: Optional[str], task: Task) -> bool:
        """Returns whether a given section name matches a task's current section"""

        # if we don't care about sections, consider them matching
        if not self.config.map_labels_to_sections:
            return True

        # task has no section (default section equates to null section)
        if not task.section_id or self.is_default_section(task.section_id, task.project_id):
            return not section

        # task has a section, but input does not
        elif not section:
            return False

        # compare the input section and the task section
        user_section = self.get_section(section, task.project_id)
        return user_section.id == task.section_id

    def _get_tasks(self, project_id: str) -> list[Task]:
        """
        Fetches a list of tasks from Todoist or from local cache

        Mutations to the list or to any tasks in the list will
        modify the local cache.

        For a safe list of tasks, see `get_tasks`
        """

        if project_id in self.project_tasks:
            return self.project_tasks[project_id]

        tasks = self._client.get_tasks(project_id=project_id)
        self.project_tasks[project_id] = tasks
        return tasks

    def get_tasks(self, project_id: str) -> list[Task]:
        """Fetches a list of tasks that can be safely mutated"""

        return deepcopy(self._get_tasks(project_id))

    def get_task(self, task_id: str, project_id: str) -> Optional[Task]:
        """Fetches a task that can be safely mutated"""

        for task in self._get_tasks(project_id):
            if task.id == task_id:
                return deepcopy(task)

        return None

    def add_task(
        self,
        content: str,
        project_id: str,
        section: Optional[str] = None,
        labels: Optional[list[str]] = None,
        description: Optional[str] = None,
        **kwargs,
    ) -> Task:
        if self.config.map_labels_to_sections:
            section_name = section or self.config.default_section_name

            api_section = self.get_section(section_name, project_id)
            kwargs["section_id"] = api_section.id

        if labels:
            kwargs["labels"] = labels

        if description and self.config.add_recipes_to_task_description:
            kwargs["description"] = description

        existing_tasks = self._get_tasks(project_id)
        new_task = self._client.add_task(content=content, project_id=project_id, **kwargs)
        existing_tasks.append(new_task)
        return deepcopy(new_task)

    def update_task(
        self,
        task_id: str,
        project_id: str,
        section: Optional[str] = None,
        labels: Optional[list[str]] = None,
        description: Optional[str] = None,
        **kwargs,
    ) -> Task:
        """
        Updates an existing task

        May also delete the existing task and create a new one with a new task id
        """

        task: Optional[Task] = None
        task_index_to_update: Optional[int] = None
        for i, local_task in enumerate(self._get_tasks(project_id)):
            if local_task.id == task_id:
                task = local_task
                task_index_to_update = i

        if not task or task_index_to_update is None:
            raise Exception("Task does not exist")

        if not labels:
            labels = task.labels

        if labels:
            kwargs["labels"] = labels

        if description and self.config.add_recipes_to_task_description:
            kwargs["description"] = description

        if self.config.map_labels_to_sections:
            if task.section_id and not section:
                section = self.get_section_by_id(task.section_id).name

            section_name = section or self.config.default_section_name
            api_section = self.get_section(section_name, project_id)
            new_section_id = api_section.id

            if new_section_id != task.section_id:
                # the Todoist API doesn't support changing sections, so we delete and re-create the task instead
                # this changes the task's id, so systems syncing with this service may need to update the id
                self.close_task(task)
                return self.add_task(
                    content=kwargs.pop("content", None) or task.content,
                    project_id=project_id,
                    section=section_name,
                    **kwargs,
                )

        is_success = self._client.update_task(task_id=task.id, project_id=project_id, **kwargs)
        if not is_success:
            raise Exception("Unable to update task; rejected by Todoist")

        updated_task = self._client.get_task(task_id)
        self._get_tasks(project_id)[task_index_to_update] = updated_task
        return deepcopy(updated_task)

    def close_task(self, task: Task) -> None:
        is_success = self._client.close_task(task.id)
        if not is_success:
            raise Exception("Unable to close task; rejected by Todoist")

        tasks = self._get_tasks(task.project_id)
        self._get_tasks(task.project_id)[:] = [local_task for local_task in tasks if local_task.id != task.id]
