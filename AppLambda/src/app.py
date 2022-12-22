from fastapi import FastAPI, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from mangum import Mangum

from .config import APP_TITLE, APP_VERSION
from .handlers.mangum import SQS
from .services.auth import AuthTokenService
from .services.core import CoreUserService, SMTPService

### App Setup ###
app = FastAPI(title=APP_TITLE, version=APP_VERSION)
app.mount("/static", StaticFiles(directory="./src/static"), name="static")
templates = Jinja2Templates(directory="./src/static/templates")

smtp_service = SMTPService()
token_service = AuthTokenService()
users_service = CoreUserService()


### Route Setup ###
from .routes import account_linking, alexa, auth, core, event_handlers, mealie, todoist

# frontend routes
app.include_router(core.frontend_router, include_in_schema=False)
app.include_router(account_linking.frontend_router, include_in_schema=False)

app.include_router(alexa.frontend_router, include_in_schema=False)
app.include_router(mealie.router, include_in_schema=False)
app.include_router(todoist.frontend_router, include_in_schema=False)

# internal routes
app.include_router(event_handlers.router, include_in_schema=False)

app.include_router(alexa.auth_router, include_in_schema=False)
app.include_router(todoist.auth_router, include_in_schema=False)

# api routes
app.include_router(account_linking.api_router)
app.include_router(auth.router)

app.include_router(alexa.list_router)
app.include_router(alexa.list_item_router)


# default route
@app.get("/", response_class=RedirectResponse, include_in_schema=False)
def home():
    return RedirectResponse(
        core.frontend_router.url_path_for("home"), status_code=status.HTTP_301_MOVED_PERMANENTLY
    )


### Lambda Handlers ###
sqs_handler = SQS.with_path(app.url_path_for("sqs_sync_event_handler"))

# this enables API Gateway to invoke our app as a Lambda function
handler = Mangum(app, custom_handlers=[sqs_handler])
