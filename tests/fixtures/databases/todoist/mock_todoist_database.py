from collections import defaultdict
from enum import Enum
from typing import Any, Optional, Type, TypeVar
from uuid import uuid4

from requests import HTTPError, Response
from todoist_api_python.models import Project, Section, Task

T = TypeVar("T")


class MockTodoistDBKey(Enum):
    projects = "projects"
    sections = "sections"
    tasks = "tasks"


class MockTodoistServer:
    def __init__(self) -> None:
        self.db: defaultdict[MockTodoistDBKey, dict[str, Any]] = defaultdict(dict[str, Any])

    @classmethod
    def _get_class_from_db_key(cls, key: MockTodoistDBKey) -> Type[object]:
        if key is MockTodoistDBKey.projects:
            return Project
        elif key is MockTodoistDBKey.sections:
            return Section
        elif key is MockTodoistDBKey.tasks:
            return Task
        else:
            raise NotImplementedError(f"{key} does not have a mapped type")

    @classmethod
    def _assert(cls, data: Optional[T]) -> T:
        if not data:
            response = Response()
            response.status_code = 404
            raise HTTPError(response=response)

        return data

    def _get_all(self, key: MockTodoistDBKey) -> list[Any]:
        return list(self.db[key].values())

    def _get_one(self, key: MockTodoistDBKey, id: str) -> Optional[Any]:
        return self.db[key].get(id)

    def _add_one(self, key: MockTodoistDBKey, data: dict[str, Any]) -> Any:
        klass = self._get_class_from_db_key(key)
        id = str(uuid4())

        data["id"] = id
        new_obj = klass.from_dict(data)  # type: ignore

        self.db[key][id] = new_obj
        return new_obj

    def _update_one(self, key: MockTodoistDBKey, obj: Any) -> None:
        assert isinstance(obj, self._get_class_from_db_key(key))
        id = getattr(obj, "id")
        self.db[key][id] = obj

    def _delete_one(self, key: MockTodoistDBKey, id: str) -> None:
        self._assert(self._get_one(key, id))
        self.db[key].pop(id)
