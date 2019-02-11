import io
import os
import json
import logging
import datetime
from requests.utils import quote
import xml.dom.minidom
import requests
from warcio.archiveiterator import ArchiveIterator


def get_rendered_original(url, type='screenshot'):
    """
    Grabs a rendered resource.

    Only reason Wayback can't do this is that it does not like the extended URIs
    i.e. 'screenshot:http://' and replaces them with 'http://screenshot:http://'
    """

    # Query URL
    qurl = "%s:%s" % (type, url)
    # Query CDX Server for the item
    #app.logger.info("Querying CDX for prefix...")
    warc_filename, warc_offset, compressedendoffset = lookup_in_cdx(qurl)

    # If not found, say so:
    if warc_filename is None:
        return None

    # Grab the payload from the WARC and return it.
    WEBHDFS_PREFIX = os.environ['WEBHDFS_PREFIX']
    url = "%s%s?op=OPEN&user.name=%s&offset=%s" % (WEBHDFS_PREFIX, warc_filename, "hdfs", warc_offset)
    if compressedendoffset:
        url = "%s&length=%s" % (url, compressedendoffset)
    #app.logger.info("Requesting copy from HDFS: %s " % url)
    r = requests.get(url, stream=True)
    #app.logger.info("Loading from: %s" % r.url)
    r.raw.decode_content = False
    #app.logger.info("Passing response to parser...")
    record = ArchiveIterator(stream=r.raw).next()
    #app.logger.info("RESULT:")
    #app.logger.info(record)

    #app.logger.info("Returning stream...")
    return record.stream, record.content_type

    #return "Test %s@%s" % (warc_filename, warc_offset)


def lookup_in_cdx(qurl):
    """
    Checks if a resource is in the CDX index.
    :return:
    """
    CDX_SERVER = os.environ['CDX_SERVER']
    query = "%s?q=type:urlquery+url:%s" % (CDX_SERVER, quote(qurl))
    r = requests.get(query)
    print(r.url)
    #logger.debug("Availability response: %d" % r.status_code)
    print(r.status_code, r.text)
    # Is it known, with a matching timestamp?
    if r.status_code == 200:
        try:
            dom = xml.dom.minidom.parseString(r.text)
            for result in dom.getElementsByTagName('result'):
                file = result.getElementsByTagName('file')[0].firstChild.nodeValue
                compressedoffset = result.getElementsByTagName('compressedoffset')[0].firstChild.nodeValue
                # Support compressed record length if present:
                if( len(result.getElementsByTagName('compressedendoffset')) > 0):
                    compressedendoffset = result.getElementsByTagName('compressedendoffset')[0].firstChild.nodeValue
                else:
                    compressedendoffset = None
                return file, compressedoffset, compressedendoffset
        except Exception as e:
            pass
            #logger.error("Lookup failed for %s!" % qurl)
            #logger.exception(e)
        #for de in dom.getElementsByTagName('capturedate'):
        #    if de.firstChild.nodeValue == self.ts:
        #        # Excellent, it's been found:
        #        return
    return None, None, None
