import re
import logging
from base64 import urlsafe_b64decode, urlsafe_b64encode
from urllib.parse import quote_plus
from requests.utils import quote

# Setup logger:
logger = logging.getLogger(f"uvicorn.error.{__name__}")

# Helper to turn timestamp etc. into full PWID:
def gen_pwid(wb14_timestamp, url, archive_id='webarchive.org.uk', scope='page', encodeBase64=True):
    # Format the PWID string:
    yy1,yy2,MM,dd,hh,mm,ss = re.findall('..', wb14_timestamp)
    iso_ts = f"{yy1}{yy2}-{MM}-{dd}T{hh}:{hh}:{ss}Z"
    pwid = f"urn:pwid:{archive_id}:{iso_ts}:page:{url}"
    
    # Encode as appropriate:
    if encodeBase64:
        pwid_enc = urlsafe_b64encode(pwid.encode('utf-8')).decode('utf-8')
        return pwid_enc
    else:
        return pwid

# Helper to parse out a PWID, optionally B64 encoded:
def parse_pwid(pwid):
    # Decode Base64 if needed
    if not pwid.startswith('urn:pwid:'):
        # Attempt to decode Base64
        try:
            decodedbytes = urlsafe_b64decode(pwid)
            decoded = decodedbytes.decode("utf-8") 
        except Exception as e:
            logger.exception("Failed to decode", e)
            decoded = ""
        # And check the result:
        if decoded.startswith('urn:pwid:'):
            pwid = decoded
        else:
           raise Exception(f'Cannot decode PWID: {pwid}')

    # Parse the PWID
    # urn:pwid:webarchive.org.uk:1995-04-18T15:56:00Z:page:http://portico.bl.uk/    
    m = re.compile('^urn:pwid:([^:]+):([^Z]+Z):([^:]+):(.+)$')
    parts = m.match(pwid)
    if not parts or len(parts.groups()) != 4:
        raise Exception(f'Cannot parse PWID: {pwid}')

    # Get the parts:
    archive = parts.group(1)
    target_date = re.sub('[^0-9]','', parts.group(2))
    scope = parts.group(3)
    url = parts.group(4)

    return archive, target_date, scope, url

