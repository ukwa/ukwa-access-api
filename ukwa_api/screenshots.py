import io
import os
import requests
import logging
import datetime
from PIL import Image
from warcio import WARCWriter
from warcio.recordloader import ArcWarcRecordLoader
from warcio.bufferedreaders import DecompressingBufferedReader

from access_api.cdx import lookup_in_cdx, list_from_cdx

# Create a logger, beneath the Uvicorn error logger:
logger = logging.getLogger(f"uvicorn.error.{__name__}")


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


def get_original(url, target_date=datetime.datetime.today()):
    # Query URL
    qurl = "url"
    # Query CDX Server for the item
    logger.debug("Querying CDX for prefix...")
    warc_filename, warc_offset, compressedendoffset = lookup_in_cdx(qurl)

    return warc_filename, warc_offset, compressedendoffset


def full_and_thumb_jpegs(large_png, crop=False):
    # Load the image and drop the alpha channel:
    img = Image.open(io.BytesIO(large_png))
    img = remove_transparency(img)
    img = img.convert("RGB")

    # Crop if needed:
    w, h = img.size
    logger.debug("IMAGE %i x %x" % (w, h))
    if crop and h > 640:
        img = img.crop((0,0,w,640))

    # Save it as a JPEG:
    out = io.BytesIO()
    img.save(out, "jpeg", quality=95)
    full_jpeg = out.getvalue()

    thumb_width = 300
    thumb_height = int((float(thumb_width) / w) * h)
    logger.debug("Got %i x %x" % (thumb_width, thumb_height))
    img.thumbnail((thumb_width, thumb_height))

    out = io.BytesIO()
    img.save(out, "jpeg", quality=95)
    thumb_jpeg = out.getvalue()

    return full_jpeg, thumb_jpeg


def remove_transparency(im, bg_colour=(255, 255, 255)):
    # Only process if image has transparency (http://stackoverflow.com/a/1963146)
    if im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info):

        # Need to convert to RGBA if LA format due to a bug in PIL (http://stackoverflow.com/a/1963146)
        alpha = im.convert('RGBA').split()[-1]

        # Create a new background image of our matt color.
        # Must be RGBA because paste requires both images have the same format
        # (http://stackoverflow.com/a/8720632  and  http://stackoverflow.com/a/9459208)
        bg = Image.new("RGBA", im.size, bg_colour + (255,))
        bg.paste(im, mask=alpha)
        return bg

    else:
        return im
