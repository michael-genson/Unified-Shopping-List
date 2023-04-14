import random
from typing import Optional

import pytest
from pytest import MonkeyPatch
from todoist_api_python.models import Project, Section, Task

from AppLambda.src.routes import account_linking
from AppLambda.src.services.todoist import TodoistTaskService
from tests.utils.generators import random_bool, random_string, random_url

from .mock_todoist_api import MockTodoistAPI, _mock_todoist_server
from .mock_todoist_database import MockTodoistDBKey, MockTodoistServer


class MockTodoistData:
    def __init__(
        self, project: Project, sections: Optional[list[Section]] = None, tasks: Optional[list[Task]] = None
    ) -> None:
        self.project = project
        self.sections = sections or []
        self.tasks = tasks or []


@pytest.fixture()
def todoist_server() -> MockTodoistServer:
    return _mock_todoist_server


@pytest.fixture()
def todoist_api() -> MockTodoistAPI:
    return MockTodoistAPI(token=random_string())


@pytest.fixture()
def todoist_data_no_sections(todoist_api: MockTodoistAPI, todoist_server: MockTodoistServer) -> list[MockTodoistData]:
    """
    Returns a list of projects and project tasks with no sections

    Every task will have `section_id` set to `None`
    """

    mock_data: list[MockTodoistData] = []
    existing_projects = todoist_api.get_projects()

    for project_counter in range(10):
        project_data = {
            "color": "grey",
            "comment_count": 0,
            "is_favorite": random_bool(),
            "is_inbox_project": False,
            "is_shared": False,
            "is_team_inbox": False,
            "name": random_string(),
            "order": project_counter + len(existing_projects),
            "url": random_url(),
            "view_style": "list",
        }

        project: Project = todoist_server._add_one(MockTodoistDBKey.projects, project_data)
        tasks = [
            todoist_api.add_task(
                content=random_string(),
                project_id=project.id,
            )
            for _ in range(10)
        ]

        mock_data.append(MockTodoistData(project=project, tasks=tasks))

    return mock_data


@pytest.fixture()
def todoist_data(todoist_server: MockTodoistServer, todoist_api: MockTodoistAPI) -> list[MockTodoistData]:
    """
    A list of projects and project tasks with sections

    Every task will have `section_id` set, but some sections may not have any tasks associated with them
    """

    mock_data: list[MockTodoistData] = []
    existing_projects = todoist_api.get_projects()

    for project_counter in range(10):
        project_data = {
            "color": "grey",
            "comment_count": 0,
            "is_favorite": random_bool(),
            "is_inbox_project": False,
            "is_shared": False,
            "is_team_inbox": False,
            "name": random_string(),
            "order": project_counter + len(existing_projects),
            "url": random_url(),
            "view_style": "list",
        }

        project: Project = todoist_server._add_one(MockTodoistDBKey.projects, project_data)
        sections = [todoist_api.add_section(name=random_string(), project_id=project.id) for _ in range(10)]
        tasks = [
            todoist_api.add_task(
                content=random_string(),
                project_id=project.id,
                section_id=random.choice(sections).id,
            )
            for _ in range(10)
        ]

        mock_data.append(MockTodoistData(project=project, sections=sections, tasks=tasks))

    return mock_data


@pytest.fixture(scope="session", autouse=True)
def mock_todoist_api():
    """Replace all Todoist API calls with locally mocked database calls"""

    mock_lambda = lambda *args, **kwargs: MockTodoistAPI(*args, **kwargs)

    mp = MonkeyPatch()
    mp.setattr(account_linking, "_get_todoist_client", mock_lambda)
    mp.setattr(TodoistTaskService, "_get_client", mock_lambda)


@pytest.fixture(autouse=True)
def clean_up_database():
    yield
    _mock_todoist_server._clear_db()
