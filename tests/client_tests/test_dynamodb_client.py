import random
from typing import Any

import pytest
from botocore.exceptions import ClientError

from AppLambda.src import config
from AppLambda.src.clients.aws import DynamoDB
from AppLambda.src.models.aws import DynamoDBAtomicOp
from tests.utils import random_email, random_int, random_string


@pytest.fixture()
def user_client() -> DynamoDB:
    return DynamoDB(config.USERS_TABLENAME, config.USERS_PK)


def test_get_item(user_client: DynamoDB):
    username = random_email()
    data = {"username": username}

    # user is not created yet
    assert not user_client.get(username)

    # create user
    user_client.put(data)
    user = user_client.get(username)
    assert user
    assert user["username"] == username

    # fetch invalid user
    assert not user_client.get(random_email())

    # create more users and make sure we still fetch the right one
    for _ in range(random_int(3, 5)):
        username = random_email()
        user_client.put({"username": username})

        user = user_client.get(username)
        assert user
        assert user["username"] == username


def test_query_item_by_secondary_index(user_client: DynamoDB):
    secondary_index = random.choice(["alexa_user_id", "todoist_user_id"])

    # create a bunch of users
    users: list[dict[str, Any]] = []
    for _ in range(random_int(3, 5)):
        user_data = {"username": random_email(), secondary_index: random_string()}
        user_client.put(user_data)
        user = user_client.get(user_data["username"])
        assert user
        users.append(user_data)

    # check that all users can be queried by their secondary index
    for user in users:
        response = user_client.query(secondary_index, user[secondary_index])
        assert len(response) == 1
        assert response[0]["username"] == user["username"]
        assert response[0][secondary_index] == user[secondary_index]

    # check that a random secondary index returns no responses
    response = user_client.query(secondary_index, random_string())
    assert not response

    # add another user with the same secondary index value and check that both are returned
    user = random.choice(users)
    common_value = user[secondary_index]

    new_user_data = {"username": random_email(), secondary_index: common_value}
    user_client.put(new_user_data)
    user = user_client.get(new_user_data["username"])
    assert user
    assert user[secondary_index] == new_user_data[secondary_index] == user[secondary_index] == common_value

    response = user_client.query(secondary_index, common_value)
    assert len(response) == 2

    # check that there are two distinct users with the correct values
    usernames = set(user["username"] for user in response)
    assert len(usernames) == 2
    for user_data in (user, new_user_data):
        assert user_data["username"] in usernames
        assert user_data[secondary_index] == common_value


def test_put_new_item(user_client: DynamoDB):
    username = random_email()
    data = {"username": username}

    user_client.put(data)
    assert user_client.get(username)


def test_put_existing_item(user_client: DynamoDB):
    username = random_email()
    first_test_attr = random_string()
    data = {"username": username, "test_attr": first_test_attr}

    user_client.put(data)
    user = user_client.get(username)
    assert user
    assert user["username"] == username
    assert user["test_attr"] == first_test_attr

    # try to update an existing user with allow_update unset
    second_test_attr = random_string()
    data["test_attr"] = second_test_attr
    with pytest.raises(ClientError):
        user_client.put(data, allow_update=False)

    # make sure the user wasn't updated
    user = user_client.get(username)
    assert user
    assert user["username"] == username
    assert user["test_attr"] == first_test_attr

    # make sure the user updates when allow_update is set
    user_client.put(data, allow_update=True)
    user = user_client.get(username)
    assert user
    assert user["username"] == username
    assert user["test_attr"] == second_test_attr


def test_atomic_operation_increment(user_client: DynamoDB):
    username = random_email()
    atomic_value = random_int(-1000, 1000)
    data = {"username": username, "atomic": atomic_value}

    user_client.put(data)
    user = user_client.get(username)
    assert user
    assert user["atomic"] == atomic_value

    change = random_int(-1000, 1000)
    response = user_client.atomic_op(username, "atomic", change, DynamoDBAtomicOp.increment)
    assert response == atomic_value + change


def test_atomic_operation_decrement(user_client: DynamoDB):
    username = random_email()
    atomic_value = random_int(-1000, 1000)
    data = {"username": username, "atomic": atomic_value}

    user_client.put(data)
    user = user_client.get(username)
    assert user
    assert user["atomic"] == atomic_value

    change = random_int(-1000, 1000)
    response = user_client.atomic_op(username, "atomic", change, DynamoDBAtomicOp.decrement)
    assert response == atomic_value - change


def test_atomic_operation_overwrite(user_client: DynamoDB):
    username = random_email()
    atomic_value = random_int(-1000, 1000)
    data = {"username": username, "atomic": atomic_value}

    user_client.put(data)
    user = user_client.get(username)
    assert user
    assert user["atomic"] == atomic_value

    new_value = random_int(-1000, 1000)
    response = user_client.atomic_op(username, "atomic", new_value, DynamoDBAtomicOp.overwrite)
    assert response == new_value


def test_atomic_operation_ensted(user_client: DynamoDB):
    username = random_email()
    atomic_value = random_int(-1000, 1000)
    data = {"username": username, "atomic": {"once_nested": {"twice_nested": atomic_value}}}

    user_client.put(data)
    user = user_client.get(username)
    assert user
    assert user["atomic"]["once_nested"]["twice_nested"] == atomic_value

    change = random_int(-1000, 1000)
    response = user_client.atomic_op(username, "atomic.once_nested.twice_nested", change, DynamoDBAtomicOp.decrement)
    assert response == atomic_value - change


def test_delete_item(user_client: DynamoDB):
    username = random_email()
    user_client.put({"username": username})
    user = user_client.get(username)
    assert user

    user_client.delete(username)
    user = user_client.get(username)
    assert not user

    # this should not raise an error
    user_client.delete(username)
    user = user_client.get(username)
    assert not user
