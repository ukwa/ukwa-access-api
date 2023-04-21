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
from datetime import datetime

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
        description="URL to look for (will [canonicalise](https://www.rfc-editor.org/rfc/rfc6596) the URL before running the query).",
        example='http://portico.bl.uk/'
    ),
    matchType: Optional[schemas.LookupMatchType] = Query(
        schemas.LookupMatchType.exact,
        # description unfortunately dupes the "Available values" list but I couldn't find a way to suppress the latter.
        description="""Type of match to look for.<br><br>
                       exact       - return captures exactly matching input url<br>
                       prefix      - return captures beginning input path<br>
                       host        - return captures belonging to input host<br>
                       domain      - as host, but also return captures belonging to subdomains<br>
                    """
       ),
    sort: Optional[schemas.LookupSort] = Query(
        schemas.LookupSort.default,
        description='Order to return results. Reverse order not recommended for large result sets.'    
        ),
    limit: Union[int, None] = Query(
        None, 
        description='Number of matching records to return.'
    ),
    # outputType: Optional[schemas.LookupOutputType] = Query(
    outputType: schemas.LookupOutputType = Query(

        schemas.LookupOutputType.cdx,
            title='',

        description='Content type returned. CDX (default) or JSON.'    
    ),
    closest: Optional[str] = Query(
        None,
        description="14-digit timestamp to aim for when sorting by Closest. Format YYYYMMDDHHMMSS.",
        regex=schemas.path_ts.regex,
        min_length=schemas.path_ts.min_length,
        max_length=schemas.path_ts.max_length
        # example omitted as we don't want it being sent through by default
    ),

    from_date: Optional[str] = schemas.create_query_from_path(schemas.path_range_ts),
    to_date: Optional[str] = schemas.create_query_from_path(schemas.path_range_ts),

    collapse_type: Optional[schemas.CollapseType] = Query(
        schemas.CollapseType.default,
        description="Collapse to the first or last unique value of the specified field."
    ),
    collapse_field: Optional[schemas.CollapseField] = Query(
        schemas.CollapseField.default,
        description="Field to collapse on if collapse_type is specified."
    ),
    collapse_length: Optional[int] = Query(
        None,
        description="Length of the value to collapse on (eg. number of leading digits in timestamp) if collapse_field is specified."
    )

):

    # Basic validation and derived parameters:
    if sort.value == "closest" and not closest:
        raise HTTPException(status_code=400, detail="Timestamp required for Closest sort.")
    if sort.value != "closest" and closest:
        raise HTTPException(status_code=400, detail="Closest Sort required for Closest Timestamp.")

    collapse_param = None
    if collapse_type in ["collapseToFirst", "collapseToLast"]:
        if collapse_field:
            if collapse_length:
                collapse_param = f"{collapse_field.value}:{collapse_length}"
            else:
                collapse_param = collapse_field.value        
        else:
            raise HTTPException(status_code=400, detail="collapse_field must be specified if collapse is specified")
    else:
        if collapse_field or collapse_length:
            raise HTTPException(status_code=400, detail="collapse_field and collapse_length can only be specified if collapse is specified")
    

    # Only put through allowed parameters:
    params = {
        'url': url,
        'matchType': matchType.value,
        'sort': sort.value,
        'limit': limit,
        'output': "json" if outputType == "json" else None,
        'closest': closest if (closest and sort.value == "closest") else None,
        'from': from_date,
        'to': to_date
        
        }
    
    if collapse_param:
        params[collapse_type] = collapse_param
    
    # Open a streaming call to cdx.api.wa.bl.uk/data-heritrix and stream the results back...
    r = requests.request(
        method='GET',
        url=f"{CDX_SERVER}",
        params=params,
        stream=True
        )
    
    # log url
    logger.info("actual request url: ")
    logger.info(r.url)
    

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
Redirect to a suitable IIIF URL using a [PWID](https://www.iana.org/assignments/urn-formal/pwid) with the given timestamp and URL properly encoded. 
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

