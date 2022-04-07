# -*- coding: utf-8 -*-
"""
This file declares the routes for the Resources module.
"""
import os
import requests
from enum import Enum
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, APIRouter, status, Request, Response, Query, Path
from fastapi.encoders import jsonable_encoder
from fastapi.responses import RedirectResponse, JSONResponse, PlainTextResponse, StreamingResponse

from pydantic import AnyHttpUrl
#from sqlalchemy.orm import Session

#from fastapi_pagination import Page, add_pagination
#from fastapi_pagination.ext.sqlalchemy import paginate

#from . import crud, models, schemas
#from .rss import ResponseFormat, nominations_to_rss
#from ..dependencies import get_db, engine

#models.Base.metadata.create_all(bind=engine)

router = APIRouter()

# Set up so objects can include links to routes
#schemas.NominationGetter.init_router(router)

# Get the location of the CDX server:
CDX_SERVER = os.environ.get("CDX_SERVER", "http://cdx.api.wa.bl.uk/data-heritrix")

class LookupMatchType(Enum):
    exact = 'exact'
    prefix = 'prefix'
    host = 'host'
    domain = 'domain'
    range = 'range'

class LookupSort(Enum):
    default = 'default'
    closest = 'closest'
    reverse = 'reverse'

@router.get("/cdx", 
    summary="Lookup Archived URLs",
    response_class=PlainTextResponse,
    description="""
 Queries our main index for URLs via the <a href="https://github.com/webrecorder/pywb/wiki/CDX-Server-API">CDX API</a>, as implemented by <a href="https://github.com/nla/outbackcdx">OutbackCDX</a> (but only exposing a subset of the [OutbackCDX API Spec.](https://nla.github.io/outbackcdx/api.html)).
 The default result format is [CDX11](https://iipc.github.io/warc-specifications/specifications/cdx-format/cdx-2015/) which has eleven space-separated fields, and looks like this:

```
uk,bl)/ 20220406141611 http://www.bl.uk/ warc/revisit 301 HLNR6AWVWYCU3YAENY3HYHLIPNWN66X7 - - 468 535573340 /heritrix/output/frequent-npld/20220227234503/warcs/BL-NPLD-20220406140340648-06556-80~npld-heritrix3-worker-1~8443.warc.gz
uk,bl)/ 20220406100614 http://www.bl.uk/ warc/revisit 301 HLNR6AWVWYCU3YAENY3HYHLIPNWN66X7 - - 469 510621199 /heritrix/output/frequent-npld/20220227234503/warcs/BL-NPLD-20220406072326912-06491-80~npld-heritrix3-worker-1~8443.warc.gz
uk,bl)/ 20220405104602 https://www.bl.uk/ text/html 200 HSJLEPFGS4K4KIDOHUYFJ3FE3EJDH7UB - - 15139 216510578 /heritrix/output/frequent-npld/20220227234503/warcs/BL-NPLD-20220405103943541-06337-80~npld-heritrix3-worker-1~8443.warc.gz
...
```

 Note that our <a href="/wayback/archive/">Wayback service</a> also supports the Memento API as per [RFC7089#4.2](https://datatracker.ietf.org/doc/html/rfc7089#section-4.2).
    """
)
async def lookup_url(
    url: AnyHttpUrl = Query(
        ...,
        title="URL to find.",
        description="URL to look for (will canonicalize the URL before running the query).",
        example='http://portico.bl.uk/'
    ),
    matchType: Optional[LookupMatchType] = Query(
        LookupMatchType.exact,
        title='Type of match to look for.'
    ),
    sort: Optional[LookupSort] = Query(
        LookupSort.default,
        title='Order to return results.'
    ),
):
    # Only put through allowed parameters:
    params = {
        'url': url,
        'matchType': matchType.value,
        'sort': sort.value
    }
    # Open a streaming call to cdx.api.wa.bl.uk/data-heritrix and stream the results back...
    r = requests.request(
        method='GET',
        url=f"{CDX_SERVER}",
        params=params,
        stream=True
        )
    return StreamingResponse(r.iter_content(chunk_size=10*1024),
                media_type=r.headers['Content-Type'])




@router.get("/resolve/{timestamp}/{url:path}",
    summary="Resolve Archived URLs",
    response_class=RedirectResponse,
    description="""
Redirects the incoming request to the most suitable archived version of a given URL, closest to the given timestamp. 

Currently redirects to the open access part of the UK Web Archive only.
    """
)
async def resolve_url(
    timestamp: str = Path(
        ...,
        title='The 14-digit timestamp to use as a target.',
        example='19950631120000',
    ),
    url: AnyHttpUrl = Path(
        ...,
        title="URL to resolve.",
        description="...",
        example='http://portico.bl.uk/',
    ),
):
    return RedirectResponse('/wayback/archive/%s/%s' % (timestamp, url))

#add_pagination(router)