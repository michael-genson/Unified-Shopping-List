import pytest

from AppLambda.src.services.auth_token import AuthTokenService
from AppLambda.src.services.rate_limit import RateLimitService
from AppLambda.src.services.smtp import SMTPService
from AppLambda.src.services.user import UserService


@pytest.fixture()
def rate_limit_service(user_service: UserService) -> RateLimitService:
    return RateLimitService(user_service)


@pytest.fixture()
def smtp_service() -> SMTPService:
    return SMTPService()


@pytest.fixture()
def token_service() -> AuthTokenService:
    return AuthTokenService()


@pytest.fixture()
def user_service(token_service: AuthTokenService) -> UserService:
    return UserService(token_service)
