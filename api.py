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
api = PatchedApi(app, version='1.0', title=os.environ.get('API_LABEL', 'UKWA API (TEST)'), doc="/doc/",
          description='API services for interacting with UKWA content. \
                      This is an early-stage prototype and may be changed without notice. \
                      TBA: A note about the separate Wayback API? <a href="http://www.mementoweb.org/guide/quick-intro/">Memento</a>')
app.config.PREFERRED_URL_SCHEME = 'https'

@app.route('/redoc/')
def redoc():
    return render_template('redoc.html')


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
        Query our CDX index.

        TBA...

        Note that our Wayback service also supports the Memento API as per https://tools.ietf.org/html/rfc7089

        """
        # Should open a streaming call to cdx.api.wa.bl.uk/data-heritrix and stream the results back...
        return ""


# ----------
# Render API
# ----------
nsr = api.namespace('Render', path="/render", description='Access to crawl-time and post-crawl screenshots of archived websites.')

@nsr.route('/')
@nsr.param('url', 'URL to look up.', required=True, location='args', default=EXAMPLE_URL)
@nsr.param('source', 'The source of the screenshot', enum=['original', 'archive'], required=False, location='args', default='original')
@nsr.param('type', 'The type of screenshot to retrieve', enum=['thumbnail', 'screenshot', 'har', 'onreadydom', 'imagemap', 'pdf'],
          required=False, location='args', default='thumbnail')
@nsr.param('target_date', 'The target date and time to use, as a 14-character (Wayback-style) timestamp (e.g. 20190101120000)', required=False, location='args' )
class Screenshot(Resource):

    @nsr.doc(id='get_rendered_original', model=RenderedPageSchema)
    @nsr.produces(['image/*'])
    @nsr.response(404, 'No screenshot for that url has been captured during crawls.')
    def get(self):
        """
        Grabs an screenshot of an web page.

        This looks for a screenshot of a web page, returning the most recent archived version by default.

        If the <tt>source</tt> is set to <tt>original</tt> the system will \
        attempt to fine a screenshot of the original web site, as seen at crawl time. If the <tt>source</tt> is set to \
        <tt>archive</tt> then a rendering of the archived version of the page will be returned instead.

        All seeds should have a <tt>screenshot</tt> - the other rendered types are usually present with the exception of 'pdf' which is under development.

        """
        url = request.args.get('url')
        type = request.args.get('type', 'screenshot')
        source = request.args.get('source', 'original')
        target_date = request.args.get('target_date', None)

        # First check with a Wayback service to see if this URL is allowed:
        # This defaults to the public OA service, to avoid accidentally making non-OA material available.
        r = requests.get("%s%s" %(WAYBACK_SERVER, url))
        if r.status_code < 200 or r.status_code >= 400:
            abort(Response(r.reason, status=r.status_code))

        # Check the cache:
        cache_tag = "%s:%s:%s:%s" % (target_date, source, type, url)
        result = screenshot_cache.get(cache_tag)
        if result is not None:
            #app.logger.info("Found in cache: %s" % qurl)
            return send_file(io.BytesIO(result['payload']), mimetype=result['content_type'])

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
            stream = io.BytesIO(r.content)
            content_type = "image/png"

        # Get the image:
        png_data = stream.read()

        # Crop
        full_jpeg, thumb_jpeg = full_and_thumb_jpegs(png_data, crop=True)
        content_type = "image/jpeg"

        # Cache and return:
        screenshot_cache.set(cache_tag, {'payload': full_jpeg, 'content_type': content_type}, timeout=60*60)
        return send_file(io.BytesIO(full_jpeg), mimetype=content_type)


@nsr.route('/list')
@nsr.param('url', 'URL to look up.', required=True, location='args', default=EXAMPLE_URL)
@nsr.param('source', 'The source of the screenshot', enum=['original', 'archive'], required=False, location='args', default='original')
@nsr.param('type', 'The type of screenshot to retrieve', enum=['thumbnail', 'screenshot', 'har', 'onreadydom', 'imagemap', 'pdf'],
          location='args', required=False, default='thumbnail')
class Screenshot(Resource):

    @nsr.doc(id='get_screenshot_list')
    def get(self):
        """
        Lists the available crawl-time screenshots
        """
        url = request.args.get('url')
        type = request.args.get('type', 'screenshot')
        source = request.args.get('source', 'original')

        # First check with a Wayback service to see if this URL is allowed:
        # This defaults to the public OA service, to avoid accidentally making non-OA material available.
        r = requests.get("%s%s" %(WAYBACK_SERVER, url))
        if r.status_code < 200 or r.status_code >= 400:
            abort(Response(r.reason, status=r.status_code))

        # Query URL
        if source == 'original':
            qurl = "%s:%s" % (type, url)

            return jsonify(list_from_cdx(qurl))
        else:
            return jsonify(list_from_cdx(url))




@nsr.route('/iiif/2/<string:pwid>/<string:region>/<string:size>/<int:rotation>/<string:quality>.<string:format>')
@nsr.param('pwid', 'A <a href="">Persistent Web IDentifier (PWID) URN</a>. Must be URL-encoded or Base64 encoded.',
          required=True, default='urn:pwid:webarchive.org.uk:1995-04-18T15:56:00Z:page:http:%2F%2F%2Fportico.bl.uk%2F')
@nsr.param('region', 'IIIF image region.', required=True, default='full')
@nsr.param('size', 'IIIF image size.', required=True, default='full')
@nsr.param('rotation', 'IIIF image rotation (degrees).', required=True, default='0')
@nsr.param('quality', 'IIIF image quality.', required=True, default='default', enum=['default', 'grey'])
@nsr.param('format', 'IIIF image format.', required=True, default='png', enum=['png','jpg'])
class IIIFRenderer(Resource):
    @ns.doc(id='iiif')
    @ns.response(200, 'The requested image, if available.')
    def get(self, pwid, region, size, rotation, quality, format):
        """
        """
        return redirect('/wayback/archive/%s/%s' % (timestamp, url), code=307)



# -------------------------------
# Statistics
# -------------------------------
nss = api.namespace('Statistics', path="/stats", description='Information and summary statistics.')

@nss.route('/crawl/recent-screenshots')
class Screenshots(Resource):

    @ns.doc(id='get_screenshots_dashboard')
    @ns.produces(['text/html'])
    def get(self):
        stats = load_stats()
        return Response(render_template('screenshots.html', title="Recent Screenshots", stats=stats), mimetype='text/html')


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

        Either way, the URL will also be posted to the Internet Archive URL Save This Page service as well.

        """
        sr = { 'url': url, 'result': {} }
        # First enqueue for crawl, if configured:
        try:
            self.launcher(url)
            sr['result']['ukwa'] = {'event': 'save-page-now',  'status': 201, 'reason': 'Crawl Requested' }
        except Exception as e:
            sr['result']['ukwa'] = {'event': 'save-page-now', 'status': 500, 'reason': e }

        # Then also submit request to IA
        try:
            ia_save_url = "https://web.archive.org/save/%s" % url
            r = requests.get(ia_save_url)
            sr['result']['ia'] = {'event': 'save-page-now',  'status': r.status_code, 'reason': r.reason }
        except Exception as e:
            sr['result']['ia'] = {'event': 'save-page-now', 'status': 500, 'reason': e }

        return jsonify(sr)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

