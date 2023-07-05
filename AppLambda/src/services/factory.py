from .auth_token import AuthTokenService
from .rate_limit import RateLimitService
from .smtp import SMTPService
from .user import UserService


class ServiceFactory:
    def __init__(self) -> None:
        self._rate_limit: RateLimitService | None = None
        self._smtp: SMTPService | None = None
        self._token: AuthTokenService | None = None
        self._user: UserService | None = None

    @property
    def rate_limit(self):
        if not self._rate_limit:
            self._rate_limit = RateLimitService(self.user)

        return self._rate_limit

    @property
    def smtp(self):
        if not self._smtp:
            self._smtp = SMTPService()

        return self._smtp

    @property
    def token(self):
        if not self._token:
            self._token = AuthTokenService()

        return self._token

    @property
    def user(self):
        if not self._user:
            self._user = UserService(self.token)

        return self._user

    def reset(self):
        self._rate_limit = None
        self._smtp = None
        self._token = None
        self._user = None
