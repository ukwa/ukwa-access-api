# -*- coding: utf-8 -*-
"""
This file declares the routes for the Mementos module.
"""
import os
import re
import logging
import requests
from enum import Enum
from typing import List, Optional, Union

from fastapi import Depends, FastAPI, HTTPException, APIRouter, status, Request, Response, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import RedirectResponse, JSONResponse, PlainTextResponse, StreamingResponse

from pydantic import AnyHttpUrl
#from sqlalchemy.orm import Session

#from fastapi_pagination import Page, add_pagination
#from fastapi_pagination.ext.sqlalchemy import paginate

from . import schemas
#from .rss import ResponseFormat, nominations_to_rss
#from ..dependencies import get_db, engine

from ..cdx import lookup_in_cdx, list_from_cdx, can_access, CDX_SERVER, get_warc_stream
#from ..screenshots import get_rendered_original_stream, full_and_thumb_jpegs
#from ..crawl_kafka import KafkaLauncher
from ..pwid import gen_pwid

#models.Base.metadata.create_all(bind=engine)

# Create a logger, beneath the Uvicorn error logger:
logger = logging.getLogger(f"uvicorn.error.{__name__}")

# Setup a router:
router = APIRouter(
    prefix='/mementos'
)

# Set up so objects can include links to routes
#schemas.NominationGetter.init_router(router)

#
#
#

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
    matchType: Optional[schemas.LookupMatchType] = Query(
        schemas.LookupMatchType.exact,
        title='Type of match to look for.'
    ),
    sort: Optional[schemas.LookupSort] = Query(
        schemas.LookupSort.default,
        title='Order to return results.'
    ),
    limit: Union[int, None] = Query(
        None, 
        title='Number of matching records to return.'
    ),
):
    # Only put through allowed parameters:
    params = {
        'url': url,
        'matchType': matchType.value,
        'sort': sort.value,
        'limit': limit,
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


#
#
#

@router.get("/resolve/{timestamp}/{url:path}",
    summary="Resolve Archived URLs",
    response_class=RedirectResponse,
    description="""
Redirects the incoming request to the most suitable archived version of a given URL, closest to the given timestamp. 

Currently redirects to the open access part of the UK Web Archive only.
    """
)
async def resolve_url(
    timestamp: str = schemas.path_ts,
    url: AnyHttpUrl = schemas.path_url,
):
    return RedirectResponse('/wayback/archive/%s/%s' % (timestamp, url), status_code=303)

#
#
#

@router.get("/warc/{timestamp}/{url:path}",
    summary="Get a WARC Record",
    response_class=StreamingResponse,
    description="""
Look up a URL and timestamp and get the corresponding raw WARC record.
    """
)
async def get_warc(
    timestamp: str = schemas.path_ts,
    url: AnyHttpUrl = schemas.path_url,
):
#    @ns.produces(['application/warc'])
#    @ns.response(200, 'The corresponding WARC record.')

        # Check access:
        logger.info("Checking %s %s" % (timestamp, url))
        can_access(url)

        # Query CDX Server for the item
        (warc_filename, warc_offset, compressed_end_offset) = lookup_in_cdx(url, timestamp)

        logger.error("Getting record: %s %s %s" % (warc_filename, warc_offset, compressed_end_offset))

        # If not found, say so:
        if warc_filename is None:
            abort(404)

        # Grab the payload from the WARC and return it.
        stream, content_type = get_warc_stream(warc_filename,warc_offset, compressed_end_offset, payload_only=False)

        # Wrap as generator
        # https://fastapi.tiangolo.com/advanced/custom-response/#using-streamingresponse-with-file-like-objects
        def iterfile():
            while True:
                chunk = stream.read(10240)
                if len(chunk) > 0:
                    yield chunk
                else:
                    break

        # Add a filename header for direct downloads:
        slug = s = re.sub('[^0-9a-zA-Z]+', '-', url)
        if 'application/warc' == content_type:
            ext = 'warc'
        else:
            ext = 'arc'
        headers = {
            'Content-Disposition': f'attachment; filename="{timestamp}_{slug}.{ext}"'
        }

        # Return the WARC stream:
        return StreamingResponse(
            iterfile(), 
            media_type=content_type,
            headers=headers,
        )


@router.get("/screenshot/{timestamp}/{url:path}",
    summary="Generate an IIIF Screenshot URL",
    response_class=RedirectResponse,
    description="""
Redirect to a suitable IIIF URL using a PWID with the given timestamp and URL properly encoded. 
    """
)
async def resolve_url(
    request: Request,
    timestamp: str = schemas.path_ts,
    url: AnyHttpUrl = schemas.path_url,
):
    pwid = gen_pwid(timestamp, url)
    iiif_url = request.url_for('iiif_renderer', pwid=pwid, region='0,0,1024,1024', size='600,', rotation=0, quality='default', format='png')
    logger.info(f"About to return {iiif_url}")
    return RedirectResponse(iiif_url, status_code=303)

