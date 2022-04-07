
import os
from fastapi import Depends, FastAPI

from .dependencies import get_db
from .nominations import router as nominations

API_VERSION = os.environ.get('API_VERSION', '0.0.0-dev')

tags_metadata = [
    {
        "name": "resources",
        "description": "Archived web resources: finding things by URL and date/time.",
        "externalDocs": {
            "description": "Resources external docs",
            "url": "https://www.webarchive.org.uk/",
        },
    },
    {
        "name": "nominations",
        "description": "Nominations: API for nominating URLs to be archived.",
    },
]

app = FastAPI(
    dependencies=[Depends(get_db)],
    title="UK Web Archive API",
    description="API services for the UK Web Archive. \n\n**This is an early-stage prototype and may be changed without notice.**",
    version=API_VERSION,
    terms_of_service="https://www.webarchive.org.uk/ukwa/info/terms_conditions",
    contact={
        "name": "Web Archivist",
        "url": "https://www.webarchive.org.uk/ukwa/contact",
        "email": "web-archivist@bl.uk",
    },
    openapi_tags=tags_metadata,
)


app.include_router(
    nominations.router,
    tags=["nominations"]
)
#app.include_router(items.router)
#app.include_router(
#    admin.router,
#    prefix="/admin",
#    tags=["admin"],
#    dependencies=[Depends(get_token_header)],
#    responses={418: {"description": "I'm a teapot"}},
#)


#@app.get("/")
#async def root():
#    return {"message": "Hello Bigger Applications!"}
