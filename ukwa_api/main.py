
import os
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles

from prometheus_fastapi_instrumentator import Instrumentator

from .dependencies import get_db
from .nominations import router as nominations
from .mementos import router as mementos
from .iiif import router as iiif

API_VERSION = os.environ.get('API_VERSION', '0.0.0-dev')

tags_metadata = [
    {
        "name": "Archived URLs",
        "description": "Find archived web resources (a.k.a. [Mementos](https://datatracker.ietf.org/doc/html/rfc7089#section-1.1)), by URL and date/time.",
        "externalDocs": {
            "description": "Corresponding User Interface",
            "url": "https://www.webarchive.org.uk/wayback/archive/",
        },
    },
    {
        "name": "Nominations",
        "description": "Nominating URLs to be archived.",
        "externalDocs": {
            "description": "Corresponding User Interface",
            "url": "https://www.webarchive.org.uk/ukwa/nominate/",
        },
    },
    {
        "name": "IIIF Image API",
        "description": "IIIF Image API for accessing screenshots of archived web pages.",
    },
    {
        "name": "Internal",
    },
]

app = FastAPI(
    dependencies=[Depends(get_db)],
    title="UK Web Archive API"
)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Add Prometheus integration:
instrumentator = Instrumentator().instrument(app).expose(app, tags=['Internal'])

#
# Add Logo.
# As per https://fastapi.tiangolo.com/advanced/extending-openapi/?h=get_swagger_ui_html#overriding-the-defaults
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="UK Web Archive API",
        description="API services for the UK Web Archive. \n\n**This is an early-stage prototype and may be changed without notice.**",
        version=API_VERSION,
        terms_of_service="https://www.webarchive.org.uk/ukwa/info/terms_conditions",
        contact={
            "name": "Web Archivist",
            "url": "https://www.webarchive.org.uk/ukwa/contact",
            "email": "web-archivist@bl.uk",
        },
        routes=app.routes,
        tags=tags_metadata,
    )
    openapi_schema["info"]["x-logo"] = {
            "url": "./static/ukwa-2018-onwhite-close.svg",
            "backgroundColor": "#FFFFFF",
            "altText": "UK Web Archive logo"
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

#
# CORS
# 
origins = [
    "*",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#
# Hook in the module routes
#
app.include_router(
    mementos.router,
    tags=["Archived URLs"],
)
app.include_router(
    iiif.router,
    tags=["IIIF Image API"],
)
app.include_router(
    nominations.router,
    tags=["Nominations"],
    dependencies=[Depends(get_db)],
)

# Just an endpoint for checking the service is up:
@app.get("/ping", include_in_schema=False)
async def root():
    return {"message": "pong!"}

