import random
from typing import Optional

import pytest
from todoist_api_python.models import Section, Task

from AppLambda.src.services.todoist import TodoistTaskService
from tests.fixtures.databases.todoist.fixture_todoist_database import MockTodoistData
from tests.fixtures.databases.todoist.mock_todoist_api import MockTodoistAPI
from tests.utils.generators import random_string

# TODO: verify service task cache is properly maintained for all operations


def test_todoist_task_service_get_section_by_id(
    todoist_task_service: TodoistTaskService, todoist_data: list[MockTodoistData]
):
    data = random.choice(todoist_data)
    assert data.sections
    for section in data.sections:
        assert todoist_task_service.get_section_by_id(section.id) == section


def test_todoist_task_service_get_section_by_name(
    todoist_task_service: TodoistTaskService, todoist_data: list[MockTodoistData]
):
    data = random.choice(todoist_data)
    assert data.sections
    for section in data.sections:
        assert todoist_task_service.get_section(section.name, project_id=data.project.id) == section

        # section name matching is case-insensitive and strips whitespace
        assert todoist_task_service.get_section(section.name.upper() + " ", data.project.id) == section


def test_todoist_task_service_get_section_by_invalid_name(
    todoist_api: MockTodoistAPI, todoist_task_service: TodoistTaskService, todoist_data: list[MockTodoistData]
):
    project = random.choice(todoist_data).project
    original_sections = todoist_api.get_sections(project_id=project.id)

    # get_section creates a new section if one doesn't exist with that name
    new_section_name = random_string()
    new_section = todoist_task_service.get_section(new_section_name, project_id=project.id)

    updated_sections = todoist_api.get_sections(project_id=project.id)
    assert len(updated_sections) == len(original_sections) + 1

    assert new_section in updated_sections
    for section in original_sections:
        assert section in updated_sections


def test_todoist_task_service_is_default_section(
    todoist_task_service: TodoistTaskService, todoist_data: list[MockTodoistData]
):
    data = random.choice(todoist_data)
    assert data.sections
    section = random.choice(data.sections)
    assert not todoist_task_service.is_default_section(section.id, data.project.id)

    default_section_name = todoist_task_service.config.default_section_name
    default_section = todoist_task_service.get_section(default_section_name, project_id=data.project.id)
    assert todoist_task_service.is_default_section(default_section.id, data.project.id)


@pytest.mark.parametrize(
    "todoist_task_service_fixture, use_sections",
    [
        ("todoist_task_service", False),
        ("todoist_task_service_use_sections", True),
    ],
)
def test_todoist_task_service_is_task_section(
    todoist_task_service_fixture: str,
    use_sections: bool,
    todoist_data: list[MockTodoistData],
    request: pytest.FixtureRequest,
):
    todoist_task_service: TodoistTaskService = request.getfixturevalue(todoist_task_service_fixture)

    data = random.choice(todoist_data)
    task, task_with_no_section, task_with_default_section = random.sample(data.tasks, 3)

    assert task.section_id
    section: Optional[Section] = None
    for _section in data.sections:
        if _section.id == task.section_id:
            section = _section

    assert section
    task_with_no_section.section_id = None

    default_section = todoist_task_service.get_section(
        todoist_task_service.config.default_section_name, data.project.id
    )
    task_with_default_section.section_id = default_section.id

    random_section = todoist_task_service.get_section(random_string(), data.project.id)

    # even when sections don't match, we consider them matching when not using sections,
    # so all of these scenarios should only be True if we are not using sections

    ## Task with Section
    assert use_sections is not todoist_task_service.is_task_section(default_section.name, task)
    assert use_sections is not todoist_task_service.is_task_section(random_section.name, task)
    assert use_sections is not todoist_task_service.is_task_section(None, task)
    assert use_sections is not todoist_task_service.is_task_section("", task)

    ## Task with No Section
    assert use_sections is not todoist_task_service.is_task_section(default_section.name, task_with_no_section)
    assert use_sections is not todoist_task_service.is_task_section(random_section.name, task_with_no_section)
    assert use_sections is not todoist_task_service.is_task_section(section.name, task_with_no_section)

    ## Task with Default Section
    # even if the section name is the default section name, we consider it
    # non-matching because the default section is effectively null
    assert use_sections is not todoist_task_service.is_task_section(default_section.name, task_with_default_section)
    assert use_sections is not todoist_task_service.is_task_section(random_section.name, task_with_default_section)
    assert use_sections is not todoist_task_service.is_task_section(section.name, task_with_default_section)

    # these scenarios should always return True, even when using sections

    ## Task with Section
    assert todoist_task_service.is_task_section(section.name, task)

    ## Task with No Section
    assert todoist_task_service.is_task_section(None, task_with_no_section)
    assert todoist_task_service.is_task_section("", task_with_no_section)

    ## Task with Default Section
    assert todoist_task_service.is_task_section(None, task_with_default_section)
    assert todoist_task_service.is_task_section("", task_with_default_section)


def test_todoist_task_service_get_tasks(
    todoist_api: MockTodoistAPI, todoist_task_service: TodoistTaskService, todoist_data: list[MockTodoistData]
):
    data = random.choice(todoist_data)
    project = data.project
    assert data.tasks

    assert todoist_api.get_tasks(project_id=project.id) == todoist_task_service.get_tasks(project_id=project.id)


def test_todoist_task_service_get_tasks_cache(
    todoist_task_service: TodoistTaskService, todoist_data: list[MockTodoistData]
):
    data = random.choice(todoist_data)
    project = data.project
    assert data.tasks

    # verify task lists are returned as deep copies, rather than as a reference
    fetched_tasks = todoist_task_service.get_tasks(project_id=project.id)
    cached_tasks = todoist_task_service.project_tasks[project.id]
    assert fetched_tasks is not cached_tasks
    for fetched_task, cached_task in zip(fetched_tasks, cached_tasks):
        assert fetched_task is not cached_task


def test_todoist_task_service_get_task(todoist_task_service: TodoistTaskService, todoist_data: list[MockTodoistData]):
    data = random.choice(todoist_data)
    project = data.project
    assert data.tasks
    task = random.choice(data.tasks)

    assert todoist_task_service.get_task(task.id, project_id=project.id) == task
    assert not todoist_task_service.get_task(random_string(), project_id=project.id)
    assert not todoist_task_service.get_task(task.id, project_id=random_string())
    assert not todoist_task_service.get_task(random_string(), project_id=random_string())


def test_todoist_task_service_get_task_cache(
    todoist_task_service: TodoistTaskService, todoist_data: list[MockTodoistData]
):
    data = random.choice(todoist_data)
    project = data.project
    assert data.tasks
    task = random.choice(data.tasks)

    # verify tasks are returned as deep copies, rather than as a reference
    fetched_task = todoist_task_service.get_task(task.id, project_id=project.id)
    cached_tasks = todoist_task_service.project_tasks[project.id]
    cached_task: Optional[Task] = None
    for _task in cached_tasks:
        if _task.id == task.id:
            cached_task = _task
            break

    assert cached_task
    assert cached_task is not fetched_task


@pytest.mark.parametrize(
    "todoist_task_service_fixture, use_sections, use_descriptions",
    [
        ("todoist_task_service", False, False),
        ("todoist_task_service_use_sections", True, False),
        ("todoist_task_service_use_sections_and_descriptions", True, True),
    ],
)
def test_todoist_task_service_add_task(
    todoist_task_service_fixture: str,
    use_sections: bool,
    use_descriptions: bool,
    todoist_data_no_sections: list[MockTodoistData],
    request: pytest.FixtureRequest,
):
    todoist_task_service: TodoistTaskService = request.getfixturevalue(todoist_task_service_fixture)

    data = random.choice(todoist_data_no_sections)
    original_tasks = todoist_task_service.get_tasks(data.project.id)

    new_content = random_string()
    new_description = random_string()
    new_labels = [random_string()]

    new_task = todoist_task_service.add_task(
        new_content, project_id=data.project.id, labels=new_labels, description=new_description
    )
    assert new_task.project_id == data.project.id
    assert new_task.content == new_content
    assert new_task.labels == new_labels
    if use_descriptions:
        assert new_task.description == new_description
    else:
        assert not new_task.description

    updated_tasks = todoist_task_service.get_tasks(data.project.id)
    assert len(updated_tasks) == len(original_tasks) + 1

    original_task_ids = {task.id for task in original_tasks}
    updated_task_ids = {task.id for task in updated_tasks}
    assert new_task.id not in original_task_ids
    assert new_task.id in updated_task_ids
    for original_task in original_tasks:
        assert original_task.id in updated_task_ids


@pytest.mark.parametrize(
    "todoist_task_service_fixture, use_sections, use_descriptions",
    [
        ("todoist_task_service", False, False),
        ("todoist_task_service_use_sections", True, False),
        ("todoist_task_service_use_sections_and_descriptions", True, True),
    ],
)
def test_todoist_task_service_add_task_with_section(
    todoist_api: MockTodoistAPI,
    todoist_task_service_fixture: str,
    use_sections: bool,
    use_descriptions: bool,
    todoist_data: list[MockTodoistData],
    request: pytest.FixtureRequest,
):
    todoist_task_service: TodoistTaskService = request.getfixturevalue(todoist_task_service_fixture)

    data = random.choice(todoist_data)
    original_sections = todoist_api.get_sections(project_id=data.project.id)

    # verify task is created with a new section
    new_section_name = random_string()
    first_new_task = todoist_task_service.add_task(
        random_string(), project_id=data.project.id, section=new_section_name
    )
    if not use_sections:
        assert not first_new_task.section_id
    else:
        assert first_new_task.section_id
        assert todoist_task_service.get_section_by_id(first_new_task.section_id).name == new_section_name

    # verify section was created
    updated_sections = todoist_api.get_sections(project_id=data.project.id)
    if not use_sections:
        assert updated_sections == original_sections
    else:
        assert len(updated_sections) == len(original_sections) + 1
        assert new_section_name in set(s.name for s in updated_sections)
        for s in original_sections:
            assert s in updated_sections

    # verify task is created with an existing section
    second_new_task = todoist_task_service.add_task(
        random_string(), project_id=data.project.id, section=new_section_name
    )
    if not use_sections:
        assert not second_new_task.section_id
    else:
        assert second_new_task.section_id == first_new_task.section_id

    # verify no new sections were created
    all_sections = todoist_api.get_sections(project_id=data.project.id)
    assert all_sections == updated_sections


def test_todoist_task_service_add_task_cache(
    todoist_task_service: TodoistTaskService, todoist_data: list[MockTodoistData]
):
    project = random.choice(todoist_data).project
    new_task = todoist_task_service.add_task(random_string(), project_id=project.id)

    # verify new tasks are returned as deep copies, rather than as a reference
    cached_tasks = todoist_task_service.project_tasks[project.id]
    cached_task: Optional[Task] = None
    for _task in cached_tasks:
        if _task.id == new_task.id:
            cached_task = _task
            break

    assert cached_task
    assert cached_task is not new_task


@pytest.mark.parametrize(
    "todoist_task_service_fixture, use_sections, use_descriptions",
    [
        ("todoist_task_service", False, False),
        ("todoist_task_service_use_sections", True, False),
        ("todoist_task_service_use_sections_and_descriptions", True, True),
    ],
)
def test_todoist_task_service_update_task(
    todoist_task_service_fixture: str,
    use_sections: bool,
    use_descriptions: bool,
    todoist_data: list[MockTodoistData],
    request: pytest.FixtureRequest,
):
    todoist_task_service: TodoistTaskService = request.getfixturevalue(todoist_task_service_fixture)

    data = random.choice(todoist_data)
    assert data.tasks
    task_to_update = random.choice(data.tasks)
    original_task = todoist_task_service.get_task(task_to_update.id, data.project.id)
    assert original_task

    with pytest.raises(Exception):
        todoist_task_service.update_task(random_string(), data.project.id)

    new_content = random_string()
    updated_task = todoist_task_service.update_task(task_to_update.id, data.project.id, content=new_content)
    assert updated_task.id == task_to_update.id
    assert updated_task.project_id == task_to_update.project_id
    assert updated_task.content == new_content != original_task.content

    # fetch the task and make sure it actually updated
    fetched_task = todoist_task_service.get_task(updated_task.id, data.project.id)
    assert fetched_task
    assert fetched_task.id == task_to_update.id
    assert fetched_task.project_id == task_to_update.project_id
    assert fetched_task.content == new_content != original_task.content


@pytest.mark.parametrize(
    "todoist_task_service_fixture, use_sections, use_descriptions",
    [
        ("todoist_task_service", False, False),
        ("todoist_task_service_use_sections", True, False),
        ("todoist_task_service_use_sections_and_descriptions", True, True),
    ],
)
def test_todoist_task_service_update_task_labels(
    todoist_task_service_fixture: str,
    use_sections: bool,
    use_descriptions: bool,
    todoist_data: list[MockTodoistData],
    request: pytest.FixtureRequest,
):
    todoist_task_service: TodoistTaskService = request.getfixturevalue(todoist_task_service_fixture)

    data = random.choice(todoist_data)
    assert data.tasks
    task_to_update = random.choice(data.tasks)
    original_task = todoist_task_service.get_task(task_to_update.id, data.project.id)
    assert original_task

    new_labels_1 = [random_string()]
    updated_task_1 = todoist_task_service.update_task(task_to_update.id, data.project.id, labels=new_labels_1)
    assert updated_task_1.id == original_task.id
    assert updated_task_1.labels == new_labels_1 != original_task.labels

    new_labels_2 = [random_string()]
    updated_task_2 = todoist_task_service.update_task(task_to_update.id, data.project.id, labels=new_labels_2)
    assert updated_task_2.id == updated_task_1.id
    assert updated_task_2.labels == new_labels_2 != updated_task_1.labels

    # verify if labels are not supplied then they're not set to None
    updated_task_3 = todoist_task_service.update_task(task_to_update.id, data.project.id)
    assert updated_task_3.id == updated_task_2.id
    assert updated_task_3.labels == updated_task_2.labels


@pytest.mark.parametrize(
    "todoist_task_service_fixture, use_sections, use_descriptions",
    [
        ("todoist_task_service", False, False),
        ("todoist_task_service_use_sections", True, False),
        ("todoist_task_service_use_sections_and_descriptions", True, True),
    ],
)
def test_todoist_task_service_update_task_description(
    todoist_task_service_fixture: str,
    use_sections: bool,
    use_descriptions: bool,
    todoist_data: list[MockTodoistData],
    request: pytest.FixtureRequest,
):
    todoist_task_service: TodoistTaskService = request.getfixturevalue(todoist_task_service_fixture)

    data = random.choice(todoist_data)
    assert data.tasks
    task_to_update = random.choice(data.tasks)
    original_task = todoist_task_service.get_task(task_to_update.id, data.project.id)
    assert original_task
    assert not original_task.description

    new_description_1 = random_string()
    updated_task_1 = todoist_task_service.update_task(task_to_update.id, data.project.id, description=new_description_1)
    assert updated_task_1.id == original_task.id
    if not use_descriptions:
        assert not updated_task_1.description
    else:
        assert updated_task_1.description == new_description_1

    new_description_2 = random_string()
    updated_task_2 = todoist_task_service.update_task(task_to_update.id, data.project.id, description=new_description_2)
    assert updated_task_2.id == updated_task_1.id
    if not use_descriptions:
        assert not updated_task_1.description
    else:
        assert updated_task_2.description == new_description_2 != updated_task_1.description

    # verify if description is not supplied then it's not reset
    updated_task_3 = todoist_task_service.update_task(task_to_update.id, data.project.id)
    assert updated_task_3.id == updated_task_2.id
    if not use_descriptions:
        assert not updated_task_1.description
    else:
        assert updated_task_3.description == updated_task_2.description


@pytest.mark.parametrize(
    "todoist_task_service_fixture, use_sections, use_descriptions",
    [
        ("todoist_task_service", False, False),
        ("todoist_task_service_use_sections", True, False),
        ("todoist_task_service_use_sections_and_descriptions", True, True),
    ],
)
def test_todoist_task_service_update_task_with_new_section(
    todoist_task_service_fixture: str,
    use_sections: bool,
    use_descriptions: bool,
    todoist_data: list[MockTodoistData],
    request: pytest.FixtureRequest,
):
    todoist_task_service: TodoistTaskService = request.getfixturevalue(todoist_task_service_fixture)

    data = random.choice(todoist_data)
    task_to_update = random.choice(data.tasks)
    assert task_to_update.section_id

    section: Optional[Section] = None
    for _section in data.sections:
        if _section.id != task_to_update.section_id:
            section = _section
            break

    assert section
    original_task = todoist_task_service.get_task(task_to_update.id, data.project.id)
    assert original_task
    assert original_task.section_id

    # verify passing no section does not change the task's section
    updated_task = todoist_task_service.update_task(task_to_update.id, data.project.id)
    assert updated_task.id == original_task.id
    assert updated_task.section_id == original_task.section_id

    # verify the section is updated
    new_section_name = random_string()
    updated_task = todoist_task_service.update_task(task_to_update.id, data.project.id, section=new_section_name)
    if not use_sections:
        assert updated_task.id == original_task.id
        assert updated_task.section_id == original_task.section_id
    else:
        new_section = todoist_task_service.get_section(new_section_name, project_id=data.project.id)
        assert updated_task.section_id == new_section.id != original_task.section_id

        # updating a task's section actually closes/deletes the existing task and adds a new task,
        # so we need to make sure that happens, as well as verifying the section has been updated
        assert updated_task.id != original_task.id
        assert updated_task.content == original_task.content
        assert not todoist_task_service.get_task(original_task.id, data.project.id)

        fetched_task = todoist_task_service.get_task(updated_task.id, data.project.id)
        assert fetched_task
        assert fetched_task.section_id == updated_task.section_id
        assert fetched_task.content == updated_task.content


@pytest.mark.parametrize(
    "todoist_task_service_fixture, use_sections, use_descriptions",
    [
        ("todoist_task_service", False, False),
        ("todoist_task_service_use_sections", True, False),
        ("todoist_task_service_use_sections_and_descriptions", True, True),
    ],
)
def test_todoist_task_service_update_task_with_no_section(
    todoist_task_service_fixture: str,
    use_sections: bool,
    use_descriptions: bool,
    todoist_data_no_sections: list[MockTodoistData],
    request: pytest.FixtureRequest,
):
    todoist_task_service: TodoistTaskService = request.getfixturevalue(todoist_task_service_fixture)

    data_with_no_sections = random.choice(todoist_data_no_sections)
    assert data_with_no_sections.tasks
    task_with_no_section = random.choice(data_with_no_sections.tasks)
    assert not task_with_no_section.section_id

    # verify updating a task with no section updates the task with the default section
    updated_task = todoist_task_service.update_task(task_with_no_section.id, data_with_no_sections.project.id)
    if not use_sections:
        assert updated_task.id == task_with_no_section.id
        assert not updated_task.section_id
    else:
        assert updated_task.section_id
        assert (
            todoist_task_service.get_section_by_id(updated_task.section_id).name
            == todoist_task_service.config.default_section_name
        )


def test_todoist_task_service_update_task_cache(
    todoist_task_service: TodoistTaskService, todoist_data: list[MockTodoistData]
):
    data = random.choice(todoist_data)
    assert data.tasks
    task_to_update = random.choice(data.tasks)

    updated_task = todoist_task_service.update_task(task_to_update.id, data.project.id, content=random_string())

    # verify updated tasks are returned as deep copies, rather than as a reference
    cached_tasks = todoist_task_service.project_tasks[data.project.id]
    cached_task: Optional[Task] = None
    for _task in cached_tasks:
        if _task.id == updated_task.id:
            cached_task = _task
            break

    assert cached_task
    assert cached_task is not updated_task


def test_todoist_task_service_close_task(todoist_task_service: TodoistTaskService, todoist_data: list[MockTodoistData]):
    data = random.choice(todoist_data)
    assert data.tasks

    # closing a task deletes it locally
    task_to_delete = random.choice(data.tasks)

    original_tasks = todoist_task_service.get_tasks(data.project.id)
    todoist_task_service.close_task(task_to_delete)
    updated_tasks = todoist_task_service.get_tasks(data.project.id)

    assert len(updated_tasks) == len(original_tasks) - 1
    original_task_ids = {task.id for task in original_tasks}
    updated_task_ids = {task.id for task in updated_tasks}

    assert task_to_delete.id in original_task_ids
    assert task_to_delete.id not in updated_task_ids
    for task_id in updated_task_ids:
        assert task_id in original_task_ids
