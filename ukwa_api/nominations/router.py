# -*- coding: utf-8 -*-
"""
This file declares the routes for the Nominations module.

The structure of this module follows:
  https://fastapi.tiangolo.com/tutorial/sql-databases/

but modularized like:
  https://fastapi.tiangolo.com/tutorial/bigger-applications/ 

"""
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, APIRouter, status, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from fastapi_pagination import Page, add_pagination
from fastapi_pagination.ext.sqlalchemy import paginate

from typing import Callable
from prometheus_fastapi_instrumentator.metrics import Info
from prometheus_client import Counter

from . import crud, models, schemas
from .rss import ResponseFormat, nominations_to_rss
from ..dependencies import get_db, engine

models.Base.metadata.create_all(bind=engine)

router = APIRouter(
    prefix="/nominations"
)

# Set up so objects can include links to routes
schemas.NominationGetter.init_router(router)

# Just creating and using metrics is sufficient for them to be included:
nominations_accepted = Counter(
    'ukwa_api_nominations_accepted', 
    'UKWA API counter of nominations accepted.'
)

# Nominating a URL, should redirect to a Nomination record (see below):
@router.post("/", 
    response_model=schemas.Nomination, 
    status_code=status.HTTP_201_CREATED,
    summary="Nominate a URL",
    description="""
Use this to nominate a URL to be archived by the UK Web Archive. 
Note that the only __required__ field is the __URL__.

If possible, you should also submit a name and email so we can get in touch with you.
You can also add a note with any further information.

All nominated _URLs_ will be publicly accessible, as will the _title_ and _tag_ fields (if any).
Any name, email or note you submit will _not_ be accessible via this API. 

    """
    )
def create_nomination(nomination: schemas.NominationCreate, response: Response, db: Session = Depends(get_db)):
    nom = crud.create_nomination(db, nomination)
    nominations_accepted.inc()
    nom.href = router.url_path_for('get_nomination', nomination_id=nom.id)
    response.headers['Location'] = nom.href
    return nom


# List nominations
@router.get("/", response_model=Page[schemas.Nomination])
def list_nominations(format: Optional[ResponseFormat] = ResponseFormat.json, db: Session = Depends(get_db)):
    #nominations = crud.get_nominations(db)
    #nominations_page = paginate(nominations)
    nominations_page = paginate(crud.query_nominations(db))
    if format == ResponseFormat.json:
        return nominations_page
    else:
        return nominations_to_rss(nominations_page.items)
    

# This should return the Nomination record, with
#   href pointing to self
#   status etc.
# but without any sensitive fields (name, email, note)
# e.g. 206c4142-ade7-4116-b434-db5cf3fb35db
# e.g. href = /nominations/206c4142-ade7-4116-b434-db5cf3fb35db
@router.get("/{nomination_id}", response_model=schemas.Nomination)
def get_nomination(nomination_id: str, request: Request, db: Session = Depends(get_db)):
    nom = crud.get_nomination(db, nomination_id)
    return nom


add_pagination(router)