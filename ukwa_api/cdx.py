import os
import logging
import datetime
import requests
import xml.dom.minidom

from fastapi import HTTPException

from requests.utils import quote
from collections import OrderedDict

from warcio.recordloader import ArcWarcRecordLoader
from warcio.bufferedreaders import DecompressingBufferedReader

# Get the Wayback endpoint to check for access rights:
# (default to OA one so we don't do the wrong thing if this is unset)
WAYBACK_SERVER = os.environ.get("WAYBACK_SERVER", "https://www.webarchive.org.uk/wayback/archive/")

# Get the location of the CDX server:
CDX_SERVER = os.environ.get("CDX_SERVER", "http://cdx.api.wa.bl.uk/data-heritrix")

# Get the WebHDFS service:
WEBHDFS_PREFIX = os.environ.get('WEBHDFS_PREFIX', 'http://warc-server.api.wa.bl.uk/webhdfs/v1/by-filename/')
WEBHDFS_USER = os.environ.get('WEBHDFS_USER', 'access')

# Formats
WAYBACK_TS_FORMAT = '%Y%m%d%H%M%S'
ISO_TS_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'

# Create a logger, beneath the Uvicorn error logger:
logger = logging.getLogger(f"uvicorn.error.{__name__}")


# Check if a URL is open access:
def can_access(url):
    """
    Checks if access to this URL is allowed.

    :return: True/False
    """
    qurl = "%s%s" %(WAYBACK_SERVER, url)
    logger.info("Checking access at %s" % qurl)
    #with httpx.AsyncClient() as client: ???
    r = requests.get(qurl)
    if r.status_code < 200 or r.status_code >= 400:
        logger.warn("Got %i %s" % (r.status_code, r.reason) )
        if r.status_code != None:
            raise HTTPException(status_code=r.status_code, detail=r.reason)
        else:
            raise HTTPException(status_code=500)

    return True


def lookup_in_cdx(qurl, target_date=None):
    """
    Checks if a resource is in the CDX index, closest to a specific date:

    :return:
    """
    matches = list_from_cdx(qurl)
    if len(matches) == 0:
        return None, None, None

    # Set up default:
    if target_date is None:
        target_dt = datetime.datetime.now()
    else:
        # Allow ISO date format, or 14-digit format:
        try:
            target_dt = datetime.datetime.strptime(target_date, ISO_TS_FORMAT)
        except:
            target_dt = datetime.datetime.strptime(target_date, WAYBACK_TS_FORMAT)

    # Go through looking for the closest match:
    matched_date = None
    matched_ts = None
    for ts in matches:
        wb_date = datetime.datetime.strptime(ts, WAYBACK_TS_FORMAT)
        logger.debug("MATCHING: %s %s %s %s" %(matched_date, target_dt, wb_date, ts))
        logger.debug("DELTA:THIS: %i" %(wb_date-target_dt).total_seconds())
        if matched_date:
            logger.debug("DELTA:MATCH: %i" % (matched_date-target_dt).total_seconds())
        if matched_date is None or abs((wb_date-target_dt).total_seconds()) < \
                abs((matched_date-target_dt).total_seconds()):
            matched_date = wb_date
            matched_ts = ts
            logger.debug("MATCHED: %s %s" %(matched_date, ts))
        logger.debug("FINAL MATCH: %s %s" %(matched_date, ts))

    return matches[matched_ts]


def list_from_cdx(qurl):
    """
    Checks if a resource is in the CDX index.

    :return: a list of matches by timestamp
    """
    query = "%s?q=type:urlquery+url:%s" % (CDX_SERVER, quote(qurl))
    logger.debug("Querying: %s" % query)
    r = requests.get(query)
    logger.debug("Availability response: %d" % r.status_code)
    result_set = OrderedDict()
    # Is it known, with a matching timestamp?
    if r.status_code == 200:
        try:
            dom = xml.dom.minidom.parseString(r.text)
            for result in dom.getElementsByTagName('result'):
                warc_file = result.getElementsByTagName('file')[0].firstChild.nodeValue
                compressed_offset = result.getElementsByTagName('compressedoffset')[0].firstChild.nodeValue
                capture_date = result.getElementsByTagName('capturedate')[0].firstChild.nodeValue
                # Support compressed record length if present:
                compressed_end_offset_elem = result.getElementsByTagName('compressedendoffset')
                if len(compressed_end_offset_elem) > 0:
                    compressed_end_offset = compressed_end_offset_elem[0].firstChild.nodeValue
                else:
                    compressed_end_offset = None
                result_set[capture_date] = warc_file, compressed_offset, compressed_end_offset
        except Exception as e:
            logger.error("Lookup failed for %s!" % qurl)
            logger.exception(e)

    return result_set

def get_warc_stream(warc_filename, warc_offset, compressedendoffset, payload_only=True):
    """
    Grabs a resource.
    """
    # If not found, say so:
    if warc_filename is None:
        return None, None

    # Grab the payload from the WARC and return it.
    url = "%s%s?op=OPEN&user.name=%s&offset=%s" % (WEBHDFS_PREFIX, warc_filename, WEBHDFS_USER, warc_offset)
    if compressedendoffset and int(compressedendoffset) > 0:
        url = "%s&length=%s" % (url, compressedendoffset)
    r = requests.get(url, stream=True)
    # We handle decoding etc.
    r.raw.decode_content = False
    logger.info("Loading from: %s" % r.url)
    logger.info("Got status code %s" % r.status_code)
    # Return the payload, or the record:
    if payload_only:
        # Parse the WARC, return the payload:
        rl = ArcWarcRecordLoader()
        record = rl.parse_record_stream(DecompressingBufferedReader(stream=r.raw))
        #return record.raw_stream, record.content_type
        return record.content_stream(), record.content_type
    else:
        # This makes sure we only get the first GZip chunk:
        s = DecompressingBufferedReader(stream=r.raw)
        #warc_record = s.read()
        return s, 'application/warc'


