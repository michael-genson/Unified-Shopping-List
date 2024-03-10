import pytest

from AppLambda.src.models.account_linking import UserMealieConfiguration
from tests.utils.generators import random_string


@pytest.mark.parametrize(
    "url_input, expected_url",
    [
        ("https://example.com/", "https://example.com/"),
        ("http://example.com/", "http://example.com/"),
        ("example.com/", "https://example.com/"),
        ("https://example.com", "https://example.com/"),
        ("http://example.com", "http://example.com/"),
        ("example.com", "https://example.com/"),
    ],
)
def test_user_mealie_configuration_sanitizes_mealie_base_url(url_input: str, expected_url: str):
    config = UserMealieConfiguration(
        base_url=url_input,
        auth_token=random_string(),
        auth_token_id=random_string(),
        notifier_id=random_string(),
        security_hash=random_string(),
    )

    assert config.base_url == expected_url
