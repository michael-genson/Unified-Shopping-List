### About ###
APP_TITLE = "Unified Shopping List"
APP_VERSION = "0.1.0"
INTERNAL_APP_NAME = "shopping_list_api"


### Database ###
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30
"""Default token expiration time in minutes"""

ACCESS_TOKEN_EXPIRE_MINUTES_TEMPORARY = 10
ACCESS_TOKEN_EXPIRE_MINUTES_LONG = 60 * 24 * 365 * 10

ACCESS_TOKEN_EXPIRE_MINUTES_REGISTRATION = 15
"""Number of minutes to keep a registration token active"""

ACCESS_TOKEN_EXPIRE_MINUTES_RESET_PASSWORD = 15
"""Number of minutes to keep a password reset token active"""

LOGIN_LOCKOUT_ATTEMPTS = 5
"""Number of incorrect login attempts before a user is locked out"""


### API ###
RATE_LIMIT_MINUTELY_READ = 60
"""Number of times per minute a "read" API can be called"""

RATE_LIMIT_MINUTELY_MODIFY = 30
"""Number of times per minute a "modify" API can be called"""

RATE_LIMIT_MINUTELY_SYNC = 60
"""Number of times per minute a sync event can be processed"""


### Alexa ###
ALEXA_SECRET_HEADER_KEY = "X-Alexa-Security-Hash"


### Mealie ###
MEALIE_INTEGRATION_ID = "shopping_list_api"
MEALIE_APPRISE_NOTIFIER_URL_TEMPLATE = (
    "jsons://{full_path}?-username={username}&-security_hash={security_hash}"
)

MEALIE_UNIT_DECIMAL_PRECISION = 3
MEALIE_UNIT_FRACTION_MAX_DENOMINATOR = 16
MEALIE_UNIT_FRACTION_ALLOW_IMPROPER = False


### Todoist ###
TODOIST_AUTH_REQUEST_URL = "https://todoist.com/oauth/authorize"
TODOIST_TOKEN_EXCHANGE_URL = "https://todoist.com/oauth/access_token"
TODOIST_SCOPE = "data:read_write,data:delete"
"""https://developer.todoist.com/guides/#step-1-authorization-request"""

TODOIST_MEALIE_LABEL = "Mealie"
