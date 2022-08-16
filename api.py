import os
import io
import re
import json
import logging
import requests
import threading
from urllib.parse import quote
from base64 import b64decode

from flask import Flask, redirect, url_for, jsonify, request, send_file, abort, render_template, Response
from flask.logging import default_handler
from flask_restx import Resource, Api, fields
from cachelib import FileSystemCache

import werkzeug
from werkzeug.middleware.proxy_fix import ProxyFix

from access_api.analysis import load_fc_analysis
from access_api.cdx import lookup_in_cdx, list_from_cdx, can_access
from access_api.screenshots import get_rendered_original_stream, full_and_thumb_jpegs
from access_api.save import KafkaLauncher

# Get the core Flask setup working:
app = Flask(__name__, template_folder='access_api/templates', static_folder='access_api/static')

# For https://stackoverflow.com/questions/23347387/x-forwarded-proto-and-flask X-Forwarded-Proto etc.
# https://werkzeug.palletsprojects.com/en/1.0.x/middleware/proxy_fix/
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_port=1, x_prefix=1) 

# Configuration options:
app.config['SECRET_KEY'] = os.environ.get('APP_SECRET', 'dev-mode-key')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['CACHE_FOLDER'] = os.environ.get('CACHE_FOLDER', '__cache__')

# Integrate with gunicorn logging if present:
if "gunicorn" in os.environ.get("SERVER_SOFTWARE", ""):
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

# Integrate root and module logging with Flask:
root = logging.getLogger()
root.addHandler(default_handler)
root.setLevel(app.logger.level)

# Set up a persistent cache for screenshots etc.
screenshot_cache = FileSystemCache(os.path.join(app.config['CACHE_FOLDER'], 'screenshot_cache'), threshold=0, default_timeout=0)

# Get the location of the web rendering server:
WEBRENDER_ARCHIVE_SERVER = os.environ.get("WEBRENDER_ARCHIVE_SERVER", "http://webrender:8010/render")

# Get the location of the CDX server:
CDX_SERVER = os.environ.get("CDX_SERVER", "http://cdx:9090/tc")

# Get the location of the IIIF server:
IIIF_SERVER= os.environ.get("IIIF_SERVER", "http://iiif:8182")

# Example URL to use
EXAMPLE_URL = "http://www.bl.uk/"

# API Doc Title
API_LABEL = os.environ.get('API_LABEL', 'UK Web Archive API (TEST)')
API_VERSION = os.environ.get('API_VERSION', '0.0.1')

# ------------------------------
# Setup index page 
# (done before RESTplus loads)
# ------------------------------
@app.route('/')
def redoc():
    return render_template('redoc.html', title=API_LABEL)

# Helper to turn timestamp etc. into full PWID:
def gen_pwid(wb14_timestamp, url, archive_id='webarchive.org.uk'):
    yy1,yy2,MM,dd,hh,mm,ss = re.findall('..', wb14_timestamp)
    iso_ts = f"{yy1}{yy2}-{MM}-{dd}T{hh}:{hh}:{ss}Z"
    pwid = f"urn:pwid:{archive_id}:{iso_ts}:page:{url}"
    return pwid    

# ------------------------------
# ------------------------------
# Now set up RESTplus:
# ------------------------------
# ------------------------------

app.config.SWAGGER_UI_DOC_EXPANSION = 'list'

# Patch the API to add additional info
# https://github.com/Colin-b/layab/blob/1b700f2681b39f77f35be56564990d6e3fe982d3/layab/flask_restx.py#L19
class PatchedApi(Api):
    def __init__(self, *args, **kwargs):
        self.extra_info = kwargs.pop("info", {})
        super().__init__(*args, **kwargs)

    @werkzeug.utils.cached_property
    def __schema__(self):
        schema = super().__schema__
        schema.setdefault("info", {}).update(self.extra_info)
        return schema

# Set up the API base:
api = PatchedApi(app, version=API_VERSION, title=API_LABEL, doc=None,
          description='API services for the UK Web Archive.<br/> \
                      <b>This is an early-stage prototype and may be changed without notice.</b>',
          info={ 
              "x-logo": {
                "url": "/ukwa/img/ukwa-2018-onwhite-close.svg",
                "backgroundColor": "#FFFFFF",
                "altText": "UK Web Archive logo"
                }
              })

app.config.PREFERRED_URL_SCHEME = 'https'

class RenderedPageSchema(fields.Raw):
    __schema_type__ = 'file'
    __schema_format__ = 'A rendered version of the given URL.'



# ------------------------------
# ------------------------------
# Access Services
# ------------------------------
# ------------------------------



# -------------------------------
# Statistics
# -------------------------------
nss = api.namespace('Statistics', path="/stats", description='Information and summary statistics.')

@nss.route('/crawl/recent-activity')
class Crawler(Resource):
    @nss.doc(id='get_recent_activity')
    @nss.produces(['application/json'])
    def get(self):
        """
        Recent crawl stats

        This returns a summary of recent crawling activity.
        """
        stats = load_fc_analysis()
        try:
            return jsonify(stats)
        except Exception as e:
            app.logger.exception("Could not jsonify stats: %s" % stats)


# ------------------------------
# Save This Page Service
# ------------------------------
nsn = api.namespace('Save', path="/save", description='Submit URLs to be archived.')

@nsn.route('/<path:url>')
class SaveThisPage(Resource):

    @nss.doc(id='save_this_page')
    @nss.produces(['application/json'])
    def get(self, url):
        """
        Save an URL

        Use this to request a URL be saved. If it's in scope for the UK Web Archive, it will be queued for crawling ASAP. If it's out of scope if will be logged for review, to see if we can include in in future.

        """
        sr = { 'url': url, 'result': {} }
        # First enqueue for crawl, if configured
        try:
            # Get the launcher:
            kl = get_kafka_launcher()
            # And enqueue:
            kl.launch(url, "save-page-now", webrender_this=True,
                                   launch_ts='now', inherit_launch_ts=False, forceFetch=True)
            kl.flush()
            # Report outcome:
            sr['result']['ukwa'] = {'event': 'save-page-now',  'status': 201, 'reason': 'Crawl Requested' }
        except Exception as e:
            app.logger.exception("Exception when saving URL!", e)
            sr['result']['ukwa'] = {'event': 'save-page-now', 'status': 500, 'reason': str(e) }

        # Then also submit request to IA
        ## Commenting out for now, as unsure if this is working properly.
        #try:
        #    ia_save_url = "https://web.archive.org/save/%s" % url
        #    r = requests.get(ia_save_url)
        #    sr['result']['ia'] = {'event': 'save-page-now',  'status': r.status_code, 'reason': r.reason }
        #except Exception as e:
        #    sr['result']['ia'] = {'event': 'save-page-now', 'status': 500, 'reason': e }

        return sr

# Get a launcher, stored in the global application context:
kafka_launcher = None
def get_kafka_launcher():
    global kafka_launcher

    # Thread-safe launcher setup:
    lock = threading.Lock()    
    with lock:
        if kafka_launcher is None:
            broker = os.environ.get('KAFKA_LAUNCH_BROKER', None)
            topic = os.environ.get('KAFKA_LAUNCH_TOPIC', None)
            if broker and topic:
                kafka_launcher = KafkaLauncher(broker, topic)

    # Raise error if not configured:
    if kafka_launcher is None:
        raise Exception("Crawl queue not available!")

    return kafka_launcher



if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

