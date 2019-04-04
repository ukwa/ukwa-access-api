import os
import requests
import logging
import datetime
from warcio.recordloader import ArcWarcRecordLoader
from warcio.bufferedreaders import DecompressingBufferedReader

from access_api.cdx import lookup_in_cdx, list_from_cdx

logger = logging.getLogger(__name__)

WEBHDFS_PREFIX = os.environ.get('WEBHDFS_PREFIX', 'http://localhost:8001/by-filename/')
WEBHDFS_USER = os.environ.get('WEBHDFS_USER', 'hdfs')

def get_rendered_original_list(url, render_type='screenshot'):
    # Query URL
    qurl = "%s:%s" % (render_type, url)

    return list_from_cdx(qurl)


def get_rendered_original(url, render_type='screenshot', target_date=datetime.datetime.today()):
    # Query URL
    qurl = "%s:%s" % (render_type, url)
    # Query CDX Server for the item
    logger.debug("Querying CDX for prefix...")
    warc_filename, warc_offset, compressedendoffset = lookup_in_cdx(qurl)

    return warc_filename, warc_offset, compressedendoffset


def get_rendered_original_stream(warc_filename, warc_offset, compressedendoffset):
    """
    Grabs a rendered resource.

    Only reason Wayback can't do this is that it does not like the extended URIs
    i.e. 'screenshot:http://' and replaces them with 'http://screenshot:http://'
    """
    # If not found, say so:
    if warc_filename is None:
        return None, None

    # Grab the payload from the WARC and return it.
    url = "%s%s?op=OPEN&user.name=%s&offset=%s" % (WEBHDFS_PREFIX, warc_filename, WEBHDFS_USER, warc_offset)
    if compressedendoffset:
        url = "%s&length=%s" % (url, compressedendoffset)
    r = requests.get(url, stream=True)
    logger.debug("Loading from: %s" % r.url)
    r.raw.decode_content = False
    rl = ArcWarcRecordLoader()
    record = rl.parse_record_stream(DecompressingBufferedReader(stream=r.raw))

    return record.raw_stream, record.content_type

