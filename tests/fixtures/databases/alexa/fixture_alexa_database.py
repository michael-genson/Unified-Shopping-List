from datetime import datetime
from uuid import uuid4

import pytest
from pytest import MonkeyPatch

from AppLambda.src.clients.alexa import ListManagerClient
from AppLambda.src.models.alexa import AlexaListItemOut, AlexaListOut, ListItemState, ListState
from tests.utils.generators import random_bool, random_int, random_string

from .mock_alexa_database import MockAlexaServer

_mock_alexa_server = MockAlexaServer()


@pytest.fixture()
def alexa_server() -> MockAlexaServer:
    return _mock_alexa_server


@pytest.fixture
def alexa_lists_with_no_items() -> list[AlexaListOut]:
    alexa_lists = [
        AlexaListOut(
            list_id=str(uuid4()),
            state=ListState.active,
            name=random_string(),
            version=random_int(1, 10),
            items=[],
        )
        for _ in range(10)
    ]

    for alexa_list in alexa_lists:
        _mock_alexa_server.db[alexa_list.list_id] = alexa_list.dict()

    return alexa_lists


@pytest.fixture
def alexa_lists_with_items() -> list[AlexaListOut]:
    alexa_lists = [
        AlexaListOut(
            list_id=str(uuid4()),
            state=ListState.active,
            name=random_string(),
            version=random_int(1, 10),
            items=[
                AlexaListItemOut(
                    id=str(uuid4()),
                    value=random_string(),
                    status=ListItemState.active if random_bool() else ListItemState.completed,
                    version=random_int(1, 10),
                    created_time=datetime.now(),
                    updated_time=datetime.now(),
                )
                for _ in range(random_int(10, 20))
            ],
        )
        for _ in range(10)
    ]

    for alexa_list in alexa_lists:
        _mock_alexa_server.db[alexa_list.list_id] = alexa_list.dict()

    return alexa_lists


@pytest.fixture(scope="session", autouse=True)
def mock_alexa_server():
    """Replace all Alexa API calls with locally mocked database calls"""

    mp = MonkeyPatch()
    mp.setattr(ListManagerClient, "_refresh_token", lambda *args, **kwargs: None)
    mp.setattr(
        ListManagerClient, "_send_message", lambda *args, **kwargs: _mock_alexa_server.send_message(*args[1:], **kwargs)
    )
    yield


@pytest.fixture(autouse=True)
def clean_up_database():
    yield
    _mock_alexa_server.db.clear()
