from pydantic import BaseSettings


class AppSecrets(BaseSettings):
    ### AWS ###
    aws_region: str = "us-east-1"

    ### Database ###
    db_secret_key: str = "CHANGE-ME"
    db_algorithm: str = "HS256"

    ### SMTP ###
    smtp_server: str = "smtp.example.com"
    smtp_port: int = 587
    smtp_sender: str = "My SMTP User"
    smtp_username: str = "my-email@example.com"
    smtp_password: str = ""

    ### Access ###
    app_client_id: str = "my-app-client-id"
    app_client_secret: str = "my-app-client-secret"
    email_whitelist: list[str] = ["my-email@example.com"]

    ### Alexa ###
    alexa_client_id: str = "my-alexa-client-id"
    alexa_client_secret: str = "my-alexa-client-secret"
    alexa_skill_id: str = "my-alexa-skill-id"

    ### Todoist ###
    todoist_client_id: str = "my-todoist-client-id"
    todoist_client_secret: str = "my-todoist-client-secret"


class AppSettings(BaseSettings):
    ### About ###
    app_title = "Unified Shopping List"
    app_version = "0.3.8"
    internal_app_name = "shopping_list_api"

    ### App ###
    sync_event_sqs_queue_name: str = ""
    sync_event_dev_sqs_queue_name = ""
    use_whitelist: bool = True

    ### Database ###
    access_token_expire_minutes: int = 60 * 24 * 30
    """Default token expiration time in minutes"""

    access_token_expire_minutes_temporary: int = 10
    access_token_expire_minutes_long: int = 60 * 24 * 365 * 10
    access_token_expire_minutes_integration: int = 60 * 24 * 365 * 100

    access_token_expire_minutes_registration: int = 15
    """Number of minutes to keep a registration token active"""

    access_token_expire_minutes_reset_password: int = 15
    """Number of minutes to keep a password reset token active"""

    login_lockout_attempts: int = 5
    """Number of incorrect login attempts before a user is locked out"""

    ### Database Definition ###
    alexa_event_callback_tablename: str = "alexa-callback-events"
    alexa_event_callback_pk: str = "event_id"

    users_tablename: str = "shopping-list-api-users"
    users_pk: str = "username"

    ### API ###
    rate_limit_minutely_read: int = 60
    """Number of times per minute a "read" API can be called"""

    rate_limit_minutely_modify: int = 30
    """Number of times per minute a "modify" API can be called"""

    rate_limit_minutely_sync: int = 60
    """Number of times per minute a sync event can be initiated"""

    ### Alexa ###
    alexa_secret_header_key: str = "X-Alexa-Security-Hash"
    alexa_internal_source_id: str = "shopping_list_api"
    alexa_api_source_id: str = "user_api"

    ### Mealie ###
    mealie_integration_id: str = "shopping_list_api"
    mealie_apprise_notifier_url_template: str = (
        "jsons://{full_path}?-username={username}&-security_hash={security_hash}"
    )

    ### Todoist ###
    todoist_auth_request_url: str = "https://todoist.com/oauth/authorize"
    todoist_token_exchange_url: str = "https://todoist.com/oauth/access_token"
    todoist_scope: str = "data:read_write,data:delete"
    """https://developer.todoist.com/guides/#step-1-authorization-request"""

    todoist_mealie_label: str = "Mealie"
