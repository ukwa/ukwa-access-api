import os
import io
import json
import requests

from flask import Flask, redirect, url_for, jsonify, request, send_file, abort, render_template, Response
from flask_restplus import Resource, Api, fields
from cachelib import FileSystemCache

try:
    # Werkzeug 0.15 and newer
    from werkzeug.middleware.proxy_fix import ProxyFix
except ImportError:
    # older releases
    from werkzeug.contrib.fixers import ProxyFix

from access_api.analysis import load_fc_analysis
from access_api.cdx import lookup_in_cdx, list_from_cdx
from access_api.screenshots import get_rendered_original_stream, full_and_thumb_jpegs
from access_api.save import KafkaLauncher

# Get the core Flask setup working:
app = Flask(__name__, template_folder='access_api/templates', static_folder='access_api/static')
app.wsgi_app = ProxyFix(app.wsgi_app) # For https://stackoverflow.com/questions/23347387/x-forwarded-proto-and-flask X-Forwarded-Proto
app.config['SECRET_KEY'] = os.environ.get('APP_SECRET', 'dev-mode-key')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['CACHE_FOLDER'] = os.environ.get('CACHE_FOLDER', '__cache__')

# Set up a persistent cache for screenshots etc.
screenshot_cache = FileSystemCache(os.path.join(app.config['CACHE_FOLDER'], 'screenshot_cache'), threshold=0, default_timeout=0)

# Get the Wayback endpoint to check for access rights:
WAYBACK_SERVER = os.environ.get("WAYBACK_SERVER", "https://www.webarchive.org.uk/wayback/archive/")

# Get the location of the web rendering server:
WEBRENDER_ARCHIVE_SERVER= os.environ.get("WEBRENDER_ARCHIVE_SERVER", "http://webrender:8010/render")

# Example URL to use
EXAMPLE_URL = "http://www.bl.uk/"

# Define this here, before RESTplus loads:
@app.route('/')
def get_index():
    stats = load_fc_analysis()
    return render_template('index.html', title="Welcome", stats=stats)


# Now set up RESTplus:
app.config.SWAGGER_UI_DOC_EXPANSION = 'list'

# Patch the API so it's visible on HTTPS/HTTP
class PatchedApi(Api):
    @property
    def specs_url(self):
        if 'HTTP_X_FORWARDED_PROTO' in os.environ:
            return url_for(self.endpoint('specs'), _external=True, _scheme=os.environ['HTTP_X_FORWARDED_PROTO'])
        else:
            return url_for(self.endpoint('specs'), _external=True)

# Set up the API base:
api = PatchedApi(app, version='1.0', title=os.environ.get('API_LABEL', 'UKWA API (TEST)'), doc=None,
          description='API services for interacting with UKWA content. \
                      This is an early-stage prototype and may be changed without notice. \
                      TBA: A note about the separate Wayback API? <a href="http://www.mementoweb.org/guide/quick-intro/">Memento</a>')
app.config.PREFERRED_URL_SCHEME = 'https'


class RenderedPageSchema(fields.Raw):
    __schema_type__ = 'file'
    __schema_format__ = 'A rendered version of the given URL.'


class JsonOrFileSchema(fields.Raw):
    __schema_type__ = 'file'
    __schema_format__ = 'A JSON object describing the location of the rendered item, or the rendered ' \
                        'version of the original URL. Determined via content negotiation.'


# ------------------------------
# Global config:
# ------------------------------
@app.after_request
def allow_cross_origin_usage(response):
    # Allow third-parties to call these APIs from different hosts:
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


# ------------------------------
# ------------------------------
# Access Services
# ------------------------------
# ------------------------------

# ---------
# Query API
# ---------
ns = api.namespace('Query', path="/query", description='Query API for finding and resolving archived URL.')

@ns.route('/resolve/<string:timestamp>/<path:url>')
@ns.param('timestamp', 'Target timestamp in 14-digit format, e.g. 20170510120000. If unspecified, will direct to the most recent archived snapshot.',
          required=True, default='20170510120000')
@ns.param('url', 'URL to find.', required=True, default='https://www.bl.uk/')
class WaybackResolver(Resource):
    @ns.doc(id='get_wayback_resolver')
    @ns.response(307, 'Redirects the incoming request to the most suitable representation of the URL. If the client is in a reading room, they will be redirected to their local acces gateway. If the client is off-site, they will be redirected to the Open UK Web Archive.')
    def get(self, timestamp, url):
        """
        Resolve a timestamp and URL via the most appropriate playback service.

        Redirects the incoming request to the most suitable archived version of a given URL. Currently redirect to the
        open access part of the UK Web Archive only.

        """
        return redirect('/wayback/archive/%s/%s' % (timestamp, url), code=307)

@ns.route('/lookup')
@ns.param('url', 'URL to look for (will canonicalize the URL before running the query).', required=True, location='args',
          default='http://portico.bl.uk/')
@ns.param('matchType', 'Type of match to look for.', enum=[ "exact", "prefix", "host", "domain", "range" ],
          required=False, location='args', default='exact')
@ns.param('sort', 'Order to return results.', enum=[ "default", "closest", "reverse"  ],
          required=False, location='args', default='default')
class CDXServer(Resource):
    @ns.doc(id='get_cdx_server')
    @ns.response(200, 'TBA...')
    def get(self):
        """
        Lookup a URL in the UK Web Archive CDX index.

        Note that our <a href="/wayback/archive/">Wayback service</a> also supports the Memento API as per https://tools.ietf.org/html/rfc7089

        """
        # Should open a streaming call to cdx.api.wa.bl.uk/data-heritrix and stream the results back...
        return ""


# ----------
# IIIF API
# ----------
nsr = api.namespace('IIIF', path="/iiif", description='Access screenshots of archived websites via the <a href="https://iiif.io/api/">IIIF</a> <a href="https://iiif.io/api/image/2.1/">Image API 2.1</a>')
@nsr.route('/2/<path:pwid>/<string:region>/<string:size>/<int:rotation>/<string:quality>.<string:format>')
@nsr.param('pwid', 'A <a href="">Persistent Web IDentifier (PWID) URN</a>. Must be twice-URL-encoded or Base64 encoded.',
          required=True, default='urn:pwid:webarchive.org.uk:1995-04-18T15:56:00Z:page:http:%2F%2F%2Fportico.bl.uk%2F')
@nsr.param('region', 'IIIF image request <a href="https://iiif.io/api/image/2.1/#region">region</a>.', required=True, default='full')
@nsr.param('size', 'IIIF image request <a href="https://iiif.io/api/image/2.1/#size">size</a>.', required=True, default='full')
@nsr.param('rotation', 'IIIF image request <a href="https://iiif.io/api/image/2.1/#rotation">rotation (degrees)</a>.', required=True, default='0')
@nsr.param('quality', 'IIIF image request <a href="https://iiif.io/api/image/2.1/#quality">quality</a>.', required=True, default='default', enum=['default', 'grey'])
@nsr.param('format', 'IIIF image request <a href="https://iiif.io/api/image/2.1/#format">format</a>.', required=True, default='png', enum=['png','jpg'])
class IIIFRenderer(Resource):
    @ns.doc(id='iiif_2')
    @ns.response(200, 'The requested image, if available.')
    def get(self, pwid, region, size, rotation, quality, format):
        """
        Provides images of rendered archived web pages a <a href="https://iiif.io/api/">IIIF</a> <a href="https://iiif.io/api/image/2.1/">Image API 2.1</a>.
        """

        # Proxy requests to IIIF server:
        resp = requests.request(
            method='GET',
            url=f"http://iiif:8182/iiif/2/{pwid}/{region}/{size}/{rotation}/{quality}.{format}",
            headers={key: value for (key, value) in request.headers if key != 'Host'}
            )

        headers = [(name, value) for (name, value) in resp.raw.headers.items()]

        response = Response(resp.content, resp.status_code, headers)
        return response



# -------------------------------
# Statistics
# -------------------------------
nss = api.namespace('Statistics', path="/stats", description='Information and summary statistics.')

@nss.route('/crawl/recent-activity')
class Crawler(Resource):
    @nss.doc(id='get_recent_activity')
    def get(self):
        """
        Summarise recent crawling activity

        This returns a summary of recent crawling activity.
        """
        stats = load_stats()
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

    kafka_launcher = None

    def launcher(self, url):
        if self.kafka_launcher is None:
            broker = os.environ.get('KAFKA_LAUNCH_BROKER', None)
            topic = os.environ.get('KAFKA_LAUNCH_TOPIC', 'fc.candidates')
            if broker:
                self.kafka_launcher = KafkaLauncher(broker, topic)

        # And set enqueue:
        self.kafka_launcher.launch(url, "save-page-now", webrender_this=True,
                                   launch_ts='now', inherit_launch_ts=False, forceFetch=True)

    @nss.doc(id='save_this_page')
    def get(self, url):
        """
        'Save This Page' service.

        Use this to request a URL be saved. If it's in scope for the UK Web Archive, it will be queued for crawling ASAP. If it's out of scope if will be logged for review, to see if we can include in in future.

        """
        sr = { 'url': url, 'result': {} }
        # First enqueue for crawl, if configured:
        try:
            self.launcher(url)
            sr['result']['ukwa'] = {'event': 'save-page-now',  'status': 201, 'reason': 'Crawl Requested' }
        except Exception as e:
            sr['result']['ukwa'] = {'event': 'save-page-now', 'status': 500, 'reason': e }

        # Then also submit request to IA
        ## Commenting out for now, as unsure if this is working properly.
        #try:
        #    ia_save_url = "https://web.archive.org/save/%s" % url
        #    r = requests.get(ia_save_url)
        #    sr['result']['ia'] = {'event': 'save-page-now',  'status': r.status_code, 'reason': r.reason }
        #except Exception as e:
        #    sr['result']['ia'] = {'event': 'save-page-now', 'status': 500, 'reason': e }

        return jsonify(sr)




# ------------------------------
# ------------------------------
# Additional Routes (non-API)
# ------------------------------
# ------------------------------

@app.route('/doc/')
def redoc():
    return render_template('redoc.html')

@app.route('/render_raw')
def render_raw():
    """
    Grabs an screenshot of an web page.

    This looks for a screenshot of a web page, returning the most recent archived version by default.

    If the <tt>source</tt> is set to <tt>original</tt> the system will \
    attempt to fine a screenshot of the original web site, as seen at crawl time. If the <tt>source</tt> is set to \
    <tt>archive</tt> then a rendering of the archived version of the page will be returned instead.

    All seeds should have a <tt>screenshot</tt> - the other rendered types are usually present with the exception of 'pdf' which is under development.

    Caching should be done up-stream.

    """
    url = request.args.get('url')
    type = request.args.get('type', 'screenshot')
    source = request.args.get('source', 'archive')
    target_date = request.args.get('target_date', None)

    # First check with a Wayback service to see if this URL is allowed:
    # This defaults to the public OA service, to avoid accidentally making non-OA material available.
    r = requests.get("%s%s" %(WAYBACK_SERVER, url))
    if r.status_code < 200 or r.status_code >= 400:
        abort(Response(r.reason, status=r.status_code))

    # Query URL
    qurl = "%s:%s" % (type, url)

    # For originals:
    if source == 'original':
        # Query CDX Server for the item
        (warc_filename, warc_offset, compressed_end_offset) = lookup_in_cdx(qurl, target_date)

        # If not found, say so:
        if warc_filename is None:
            abort(404)

        # Grab the payload from the WARC and return it.
        stream, content_type = get_rendered_original_stream(warc_filename,warc_offset, compressed_end_offset)
    else:
        # Get rendered version from internal API
        r = requests.get(WEBRENDER_ARCHIVE_SERVER,
                            params={ 'url': url, 'show_screenshot': True, 'target_date': target_date })
        if r.status_code != 200:
            abort(Response(r.reason, status=r.status_code))
        stream = io.BytesIO(r.content)
        content_type = "image/png"

    # And return
    return send_file(stream, mimetype=content_type)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

