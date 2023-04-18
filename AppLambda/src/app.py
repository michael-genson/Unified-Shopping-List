import os
import pathlib

from fastapi import FastAPI, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from mangum import Mangum

from . import app_settings
from .handlers.mangum import SQS

### App Setup ###
current_dir = str(pathlib.Path(__file__).parent.resolve())

secrets = app_settings.AppSecrets()
settings = app_settings.AppSettings()

app = FastAPI(title=settings.app_title, version=settings.app_version)
app.mount("/static", StaticFiles(directory=os.path.join(current_dir, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(current_dir, "static/templates"))


### Service Setup ###
from .services.factory import ServiceFactory  # noqa: E402

services = ServiceFactory()


### Route Setup ###
from .routes import account_linking, alexa, auth, core, event_handlers, mealie, todoist  # noqa: E402

# frontend routes
app.include_router(core.router, include_in_schema=False)
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
app.include_router(alexa.api_router)


# default route
@app.get("/", response_class=RedirectResponse, include_in_schema=False)
def home():
    return RedirectResponse(core.router.url_path_for("home"), status_code=status.HTTP_301_MOVED_PERMANENTLY)


### Lambda Handlers ###
sqs_handler = SQS.with_path(app.url_path_for("sqs_sync_event_handler"))

# this enables API Gateway to invoke our app as a Lambda function
handler = Mangum(app, custom_handlers=[sqs_handler])
