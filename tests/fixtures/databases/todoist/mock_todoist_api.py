from datetime import datetime
from typing import Optional

from requests import HTTPError
from todoist_api_python.models import Project, Section, Task

from tests.utils import random_url

from .mock_todoist_database import MockTodoistDBKey, MockTodoistServer

_mock_todoist_server = MockTodoistServer()


class MockTodoistAPI:
    def __init__(self, token: str, *args, **kwargs) -> None:
        self.token = token

        # all Todoist instances start with an inbox project
        inbox_project: Project = _mock_todoist_server._add_one(
            MockTodoistDBKey.projects,
            {
                "color": "grey",
                "comment_count": 0,
                "is_favorite": True,
                "is_inbox_project": True,
                "is_shared": False,
                "is_team_inbox": False,
                "name": "Inbox",
                "order": 0,
                "url": random_url(),
                "view_style": "list",
            },
        )

        self.inbox_project_id = inbox_project.id

    def get_project(self, project_id: str) -> Optional[Project]:
        project: Optional[Project] = _mock_todoist_server._get_one(MockTodoistDBKey.projects, project_id)
        return project

    def get_projects(self, **kwargs) -> list[Project]:
        all_projects: list[Project] = _mock_todoist_server._get_all(MockTodoistDBKey.projects)
        for k, v in kwargs.items():
            all_projects = [project for project in all_projects if v is not None and getattr(project, k) == v]

        return all_projects

    def get_section(self, section_id: str) -> Optional[Section]:
        section: Optional[Section] = _mock_todoist_server._get_one(MockTodoistDBKey.sections, section_id)
        return section

    def get_sections(self, **kwargs) -> list[Section]:
        all_sections: list[Section] = _mock_todoist_server._get_all(MockTodoistDBKey.sections)
        for k, v in kwargs.items():
            all_sections = [section for section in all_sections if v is not None and getattr(section, k) == v]

        return all_sections

    def add_section(self, name: str, project_id: str, **kwargs) -> Section:
        _mock_todoist_server._assert(_mock_todoist_server._get_one(MockTodoistDBKey.projects, project_id))
        existing_sections = self.get_sections(project_id=project_id)
        data = {"name": name, "order": len(existing_sections), "project_id": project_id} | {
            k: v for k, v in kwargs.items() if v is not None
        }
        new_section: Section = _mock_todoist_server._add_one(MockTodoistDBKey.sections, data)
        return new_section

    def get_task(self, task_id: str) -> Task:
        task: Task = _mock_todoist_server._assert(_mock_todoist_server._get_one(MockTodoistDBKey.tasks, task_id))
        return task

    def get_tasks(self, **kwargs) -> list[Task]:
        all_tasks: list[Task] = _mock_todoist_server._get_all(MockTodoistDBKey.tasks)
        for k, v in kwargs.items():
            all_tasks = [task for task in all_tasks if v is not None and getattr(task, k) == v]

        return all_tasks

    def add_task(self, content: str, **kwargs) -> Task:
        # the API will choose the inbox id by default
        if "project_id" not in kwargs:
            kwargs["project_id"] = self.inbox_project_id
        else:
            _mock_todoist_server._assert(_mock_todoist_server._get_one(MockTodoistDBKey.projects, kwargs["project_id"]))

        existing_tasks = self.get_tasks(project_id=kwargs["project_id"])

        # we don't actually know the user id, so we use the token to be internally consistent
        defaults = {
            "assigner_id": self.token,
            "assignee_id": self.token,
            "comment_count": 0,
            "is_completed": False,
            "content": content,
            "created_at": datetime.now().isoformat(),
            "creator_id": self.token,
            "description": "",
            "labels": [],
            "order": len(existing_tasks),
            "priority": 1,
            "url": random_url(),
        }
        data = defaults | {k: v for k, v in kwargs.items() if v is not None}

        new_task: Task = _mock_todoist_server._add_one(MockTodoistDBKey.tasks, data)
        return new_task

    def update_task(self, task_id: str, allow_protected_fields=False, **kwargs) -> bool:
        try:
            existing_task = self.get_task(task_id)
            for k, v in kwargs.items():
                if not allow_protected_fields:
                    assert k not in [
                        "assigner_id",
                        "comment_count",
                        "is_completed",
                        "created_at",
                        "creator_id",
                        "id",
                        "parent_id",
                        "url",
                        "sync_id",
                    ]
                setattr(existing_task, k, v)
        except HTTPError:
            return False

        return True

    def close_task(self, task_id: str) -> bool:
        return self.update_task(task_id, allow_protected_fields=False, is_completed=True)

    def delete_task(self, task_id: str) -> bool:
        try:
            _mock_todoist_server._delete_one(MockTodoistDBKey.tasks, task_id)
        except HTTPError:
            return False

        return True
