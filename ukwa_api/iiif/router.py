# -*- coding: utf-8 -*-
"""
This file declares the routes for the IIIF module.
"""
import os
import io
import logging
from enum import Enum
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, APIRouter, status, Request, Response, Query, Path
from fastapi.encoders import jsonable_encoder
from fastapi.responses import RedirectResponse, JSONResponse, PlainTextResponse, StreamingResponse, Response

from pydantic import AnyHttpUrl

from cachelib import FileSystemCache
import httpx

#from ..cdx import lookup_in_cdx, list_from_cdx, can_access, CDX_SERVER, get_warc_stream
from ..mementos.schemas import path_ts, path_url
from ..cdx import can_access
from ..pwid import gen_pwid, parse_pwid

#from . import schemas

# Default timeout for long operations
TIMEOUT = 5.0*60

# Create a logger, beneath the Uvicorn error logger:
logger = logging.getLogger(f"uvicorn.error.{__name__}")

# Setup a router:
router = APIRouter(
    prefix='/iiif'
)

# Set up a persistent cache for screenshots etc.
CACHE_FOLDER = os.environ.get("CACHE_FOLDER", ".")
screenshot_cache = FileSystemCache(os.path.join(CACHE_FOLDER, 'screenshot_cache'), threshold=0, default_timeout=0)

# Get the location of the web rendering server:
WEBRENDER_ARCHIVE_SERVER = os.environ.get("WEBRENDER_ARCHIVE_SERVER", "http://webrender:8010/render")

# Get the location of the IIIF server:
IIIF_SERVER= os.environ.get("IIIF_SERVER", "http://iiif:8182")


#
#
#

@router.get("/helper/{timestamp}/{url:path}",
    summary="Generate an IIIF Screenshot URL",
    response_class=RedirectResponse,
    description="""
Redirect to a suitable IIIF URL using a PWID with the given timestamp and URL properly encoded. 
    """
)
async def resolve_url(
    timestamp: str = path_ts,
    url: AnyHttpUrl = path_url,
):
    pwid = gen_pwid(timestamp, url)
    iiif_url = router.url_path_for('iiif_renderer', pwid=pwid, region='0,0,1024,1024', size='600,', rotation=0, quality='default', format='png')
    logger.info(f"About to return {iiif_url}")
    return RedirectResponse(iiif_url)


#
#
#

'''
nsr = api.namespace('IIIF', path="/iiif", description='Access screenshots of archived websites via the <a href="https://iiif.io/api/">IIIF</a> <a href="https://iiif.io/api/image/2.1/">Image API 2.1</a>')
@nsr.route('/2/<path:pwid>/<string:region>/<string:size>/<int:rotation>/<string:quality>.<string:format>', merge_slashes=False)
@nsr.param('format', 'IIIF image request <a href="https://iiif.io/api/image/2.1/#format">format</a>.', required=True, default='png', enum=['png','jpg'])
@nsr.param('quality', 'IIIF image request <a href="https://iiif.io/api/image/2.1/#quality">quality</a>.', required=True, default='default', enum=['default', 'grey'])
@nsr.param('rotation', 'IIIF image request <a href="https://iiif.io/api/image/2.1/#rotation">rotation (degrees)</a>.', required=True, default='0')
@nsr.param('size', 'IIIF image request <a href="https://iiif.io/api/image/2.1/#size">size</a>.', required=True, default='full')
@nsr.param('region', 'IIIF image request <a href="https://iiif.io/api/image/2.1/#region">region</a>.', required=True, default='full')
@nsr.param('pwid', 'A <a href="https://tools.ietf.org/html/draft-pwid-urn-specification-09">Persistent Web IDentifier (PWID) URN</a>. The identifier must be URL-encoded or Base64 encoded UTF-8 text. <br/>For example, the pwid <br/>`urn:pwid:webarchive.org.uk:1995-04-18T15:56:00Z:page:http://portico.bl.uk/`<br/> must be encoded as: <br/><tt>urn%3Apwid%3Awebarchive.org.uk%3A1995-04-18T15%3A56%3A00Z%3Apage%3Ahttp%3A%2F%2Fportico.bl.uk%2F</tt><br/> or in Base64 as: <br>`dXJuOnB3aWQ6d2ViYXJjaGl2ZS5vcmcudWs6MTk5NS0wNC0xOFQxNTo1NjowMFo6cGFnZTpodHRwOi8vcG9ydGljby5ibC51ay8=`',
    example='urn%3Apwid%3Awebarchive.org.uk%3A1995-04-18T15%3A56%3A00Z%3Apage%3Ahttp%3A%2F%2Fportico.bl.uk%2F',
    required=True)
class IIIFRenderer(Resource):
    @nsr.doc(id='iiif_2', model=RenderedPageSchema)
    @nsr.produces(['image/png', 'image/jpeg'])
    @nsr.response(200, 'The requested image, if available.')
    def get(self, pwid, region, size, rotation, quality, format):
        """
        IIIF images

        Access images of rendered archived web pages via the <a href="https://iiif.io/api/">IIIF</a> <a href="https://iiif.io/api/image/2.1/">Image API 2.1</a>.
        """
 
        logger.info("IIIF PWID: %s" % pwid)

        # Re-encode the PWID for passing on:
        pwid_encoded = quote(pwid, safe='')

        # Proxy requests to IIIF server:
        resp = requests.request(
            method='GET',
            url=f"{IIIF_SERVER}/iiif/2/{pwid_encoded}/{region}/{size}/{rotation}/{quality}.{format}",
            headers={key: value for (key, value) in request.headers if key != 'Host'}
            )

        headers = [(name, value) for (name, value) in resp.headers.items()]

        response = Response(resp.content, resp.status_code, headers)
        return response

'''


@router.get("/2/{pwid}/{region}/{size}/{rotation}/{quality}.{format}",
    summary="Get Image",
    #response_class=,
    description="""
    """
)
async def iiif_renderer(
    pwid, region, size, rotation, quality, format, request: Request
):
    logger.info(f"iiif_renderer received pwid={pwid}")

    # Re-encode the PWID for passing on (no-op on base64 encoded ones):
    #pwid_encoded = quote(pwid, safe='')

    logger.debug(request.headers)

    proxies = {
        "http://": None,
        "https://": None,
    }

    # Proxy requests to IIIF server:
    iiif_url = f"{IIIF_SERVER}/iiif/2/{pwid}/{region}/{size}/{rotation}/{quality}.{format}"
    logger.info(f"Getting iiif_url {iiif_url}")
    async with httpx.AsyncClient(proxies=proxies) as client:
        r = await client.get(
            url=iiif_url,
            headers={key: value for (key, value) in request.headers.items() if key != 'Host'},
            timeout=TIMEOUT,
            )
    # Grab the headers:
    headers = [(name, value) for (name, value) in r.headers.items()]

    # Just pass the response back:
    response = Response(content=r.content, status_code=r.status_code, headers=r.headers)
    return response




'''
@nsr.route('/2/<path:pwid>/info.json', merge_slashes=False)
@nsr.param('pwid', 'A <a href="https://tools.ietf.org/html/draft-pwid-urn-specification-09">Persistent Web IDentifier (PWID) URN</a>. The identifier should be URL-encoded (or Base64 encoded) UTF-8 text. <br/>For example, the pwid <br/>`urn:pwid:webarchive.org.uk:1995-04-18T15:56:00Z:page:http://portico.bl.uk/`<br/> must be encoded as: <br/><tt>urn%3Apwid%3Awebarchive.org.uk%3A1995-04-18T15%3A56%3A00Z%3Apage%3Ahttp%3A%2F%2Fportico.bl.uk%2F</tt><br/> or in Base64 as: <br>`dXJuOnB3aWQ6d2ViYXJjaGl2ZS5vcmcudWs6MTk5NS0wNC0xOFQxNTo1NjowMFo6cGFnZTpodHRwOi8vcG9ydGljby5ibC51ay8=`',
    example='urn%3Apwid%3Awebarchive.org.uk%3A1995-04-18T15%3A56%3A00Z%3Apage%3Ahttp%3A%2F%2Fportico.bl.uk%2F',
    required=True)
class IIIFInfo(Resource):
    @nsr.doc(id='iiif_2_info', vendor={
        'x-codeSamples': [{
            'lang': 'Shell',
            'source': 'curl https://www.webarchive.org.uk/api/iiif/2/urn%3Apwid%3Awebarchive.org.uk%3A1995-04-18T15%3A56%3A00Z%3Apage%3Ahttp%3A%2F%2Fportico.bl.uk%2F/info.json'
        }]
    })
    @nsr.produces(['application/json'])
    @nsr.response(200, 'The info.json for this image')
    def get(self, pwid):
        """
        IIIF info

        Access information about images of rendered archived web pages via the <a href="https://iiif.io/api/">IIIF</a> <a href="https://iiif.io/api/image/2.1/#image-information-request-uri-syntax">Image API 2.1</a>.
        """
 
        logger.info("IIIF PWID: %s" % pwid)

        # Re-encode the PWID for passing on:
        pwid_encoded = quote(pwid, safe='')

        # Proxy requests to IIIF server:
        resp = requests.request(
            method='GET',
            url=f"{IIIF_SERVER}/iiif/2/{pwid_encoded}/info.json",
            headers={key: value for (key, value) in request.headers if key != 'Host'}
            )

        headers = [(name, value) for (name, value) in resp.headers.items()]

        response = Response(resp.content, resp.status_code, headers)
        return response

'''


# ------------------------------
# ------------------------------
# Additional Routes (non-API)
# ------------------------------
# ------------------------------

@router.get('/render_raw', include_in_schema=False)
async def render_raw(
    pwid: str,
    target_date: Optional[str] = None,
    type = 'screenshot',
    source = 'archive',
):
    """
    Creates an screenshot of an web page, or pulls one from a WARC.

    It is called indirectly by the IIIF service (which does all the Image API work), which itself is called from the iiif_renderer above. 

    This looks for a screenshot of a web page, returning the most recent archived version by default.

    If the <tt>source</tt> is set to <tt>original</tt> the system will \
    attempt to fine a screenshot of the original web site, as seen at crawl time. If the <tt>source</tt> is set to \
    <tt>archive</tt> then a rendering of the archived version of the page will be returned instead.

    All seeds should have a <tt>screenshot</tt> - the other rendered types are usually present with the exception of 'pdf' which is under development.

    Caching should be done downstream, but some caching is done here as the current IIIF server seems to fetch twice.

    """

    # Must have a pwid:
    if not pwid:
        raise HTTPException(status_code=400, detail='Must specify a PWID')

    archive, target_date, scope, url = parse_pwid(pwid)

    # Not all archives...
    if archive != 'webarchive.org.uk':
        raise HTTPException(status_code=400, detail=f'Only webarchive.org.uk PWIDs are supported.')

    # Not all scopes...
    if scope != 'page':
        raise HTTPException(status_code=400, detail=f'Only page scope PWIDs are supported.')

    # Convert https to http as the screenshotter doesn't like it with pywb it seems:
    if url.startswith('https:'):
        url = url.replace('https', 'http', 1)

    # Check with a Wayback service to see if this URL is allowed:
    if not can_access(url):
        # ABORT actually handled in can_access
        raise HTTPException(status_code=452, detail='This PWID is not available for legal reasons.')

    # Rebuild the PWID:
    pwid = gen_pwid(target_date, url)
    logger.info("Generated PWID: %s" % pwid)

    # Use cached value if there is one, using pwid as key:
    result = screenshot_cache.get(pwid)
    if result is not None:
        logger.info("Found in cache: %s" % pwid)
        #logger.info(result)
        return StreamingResponse(io.BytesIO(result['payload']), media_type=result['content_type'])

    # For originals:
    if source == 'original':
        # Query CDX Server for the item
        qurl = "%s:%s" % (type, url)
        (warc_filename, warc_offset, compressed_end_offset) = lookup_in_cdx(qurl, target_date)

        # If not found, say so:
        if warc_filename is None:
            raise HTTPException(status_code=404, detail='Not found')

        # Grab the payload from the WARC and return it.
        stream, content_type = get_rendered_original_stream(warc_filename,warc_offset, compressed_end_offset)
    else:
        # Get rendered version from internal API
        logger.info("Requesting screenshot...")
        async with httpx.AsyncClient() as client:
            r = await client.get(WEBRENDER_ARCHIVE_SERVER,
                            params={ 'url': url, 'show_screenshot': True, 'target_date': target_date },
                            timeout=TIMEOUT)
        
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=r.reason_phrase)

        logger.info("Renderer responded 200 OK!")
        stream = io.BytesIO(r.content)
        content_type = "image/png"

    # And return
    image_file = stream.read()
    screenshot_cache.set(pwid, {'payload': image_file, 'content_type': content_type}, timeout=60*60)
    return StreamingResponse(io.BytesIO(image_file), media_type=content_type)
