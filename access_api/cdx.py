import os
import logging
import datetime
from requests.utils import quote
import xml.dom.minidom
import requests
from collections import OrderedDict

WAYBACK_TS_FORMAT = '%Y%m%d%H%M%S'
ISO_TS_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'
CDX_SERVER = os.environ.get('CDX_SERVER','http://localhost:9090/fc')

logger = logging.getLogger(__name__)


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
