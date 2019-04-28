import os
import io
import json
import requests

from flask import Flask, redirect, url_for, jsonify, request, send_file, abort, render_template, Response
from flask_restplus import Resource, Api, fields
from werkzeug.contrib.cache import FileSystemCache

try:
    # Werkzeug 0.15 and newer
    from werkzeug.middleware.proxy_fix import ProxyFix
except ImportError:
    # older releases
    from werkzeug.contrib.fixers import ProxyFix

from access_api.kafka_client import CrawlLogConsumer
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
EXAMPLE_URL = "http://portico.bl.uk/"

# Define this here, before RESTplus loads:
@app.route('/')
def get_index():
    global consumer
    stats = consumer.get_stats()
    return render_template('index.html', title="Welcome", stats=stats)


# Now set up RESTplus:
app.config.SWAGGER_UI_DOC_EXPANSION = 'list'
api = Api(app, version='1.0', title='UKWA API (%s)' % os.environ.get('API_LABEL', 'TEST'), doc='/apidoc/',
          description='API services for interacting with UKWA content. \
                      This is an early-stage prototype and may be changed without notice.')


class RenderedPageSchema(fields.Raw):
    __schema_type__ = 'file'
    __schema_format__ = 'A rendered version of the given URL.'


class JsonOrFileSchema(fields.Raw):
    __schema_type__ = 'file'
    __schema_format__ = 'A JSON object describing the location of the rendered item, or the rendered ' \
                        'version of the original URL. Determined via content negociation.'


# ------------------------------
# Shared reference to Kafka consumer:
# ------------------------------
global consumer


@app.before_first_request
def start_up_kafka_client():
    # Set up the crawl log sampler
    kafka_broker = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    kafka_crawled_topic = os.environ.get('KAFKA_CRAWLED_TOPIC', 'uris.crawled.fc')
    kafka_seek_to_beginning = os.environ.get('KAFKA_SEEK_TO_BEGINNING', False)
    # Note that care needs to be taken us using Group IDs, or different workers see different parts of the logs
    global consumer
    consumer = CrawlLogConsumer(
        kafka_crawled_topic, [kafka_broker], None,
        from_beginning=kafka_seek_to_beginning)
    consumer.start()


@app.after_request
def allow_cross_origin_usage(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


# ------------------------------
# Access Services
# ------------------------------
ns = api.namespace('access', description='Access Services')


@ns.route('/resolve/<string:timestamp>/<path:url>')
@ns.param('timestamp', 'Target timestamp in 14-digit format, e.g. 20170510120000. If unspecified, will direct to the most recent archived snapshot.',
          required=True, default='20170510120000')
@ns.param('url', 'URL to look up.', required=True, default='https://www.bl.uk/')
class WaybackResolver(Resource):
    @ns.doc(id='get_wayback_resolver')
    @ns.response(307, 'Redirects the incoming request to the most suitable representation of the URL. If the client is in a reading room, they will be redirected to their local acces gateway. If the client is off-site, they will be redirected to the Open UK Web Archive.')
    def get(self, timestamp, url):
        """
        Resolve a timestamp and URL via the most appropriate playback service.

        Redirects the incoming request to the most suitable archived version of a given URL. Currently redirect to the
        open access part of the UK Web Archive only.

        """
        return redirect('https://www.webarchive.org.uk/wayback/archive/%s/%s' % (timestamp, url), code=307)


@ns.route('/screenshot/')
@ns.param('url', 'URL to look up.', required=True, location='args', default=EXAMPLE_URL)
@ns.param('source', 'The source of the screenshot', enum=['original', 'archive'], required=False, location='args', default='original')
@ns.param('type', 'The type of screenshot to retrieve', enum=['thumbnail', 'screenshot', 'har', 'onreadydom', 'imagemap', 'pdf'],
          required=False, location='args', default='thumbnail')
@ns.param('target_date', 'The target date and time to use, as a 14-character (Wayback-style) timestamp (e.g. 20190101120000)', required=False, location='args' )
class Screenshot(Resource):

    @ns.doc(id='get_rendered_original', model=RenderedPageSchema)
    @ns.produces(['image/*'])
    @ns.response(404, 'No screenshot for that url has been captured during crawls.')
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


@ns.route('/screenshot/list')
@ns.param('url', 'URL to look up.', required=True, location='args', default=EXAMPLE_URL)
@ns.param('source', 'The source of the screenshot', enum=['original', 'archive'], required=False, location='args', default='original')
@ns.param('type', 'The type of screenshot to retrieve', enum=['thumbnail', 'screenshot', 'har', 'onreadydom', 'imagemap', 'pdf'],
          location='args', required=False, default='thumbnail')
class Screenshot(Resource):

    @ns.doc(id='get_screenshot_list')
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



# -------------------------------
# Statistics & Reporting
# -------------------------------
nss = api.namespace('stats', description='Statistics & Reporting')


@nss.route('/crawler/recent-screenshots')
class Screenshots(Resource):

    @ns.doc(id='get_screenshots_dashboard')
    @ns.produces(['text/html'])
    def get(self):
        global consumer
        stats = consumer.get_stats()
        return Response(render_template('screenshots.html', title="Recent Screenshots", stats=stats), mimetype='text/html')


@nss.route('/crawler/recent-activity')
class Crawler(Resource):
    @nss.doc(id='get_recent_activity')
    def get(self):
        """
        Summarise recent crawling activity

        This returns a summary of recent crawling activity.
        """
        global consumer
        stats = consumer.get_stats()
        try:
            return jsonify(stats)
        except Exception as e:
            app.logger.exception("Could not jsonify stats: %s" % stats)


# ------------------------------
# Save This Page Service
# ------------------------------
nsn = api.namespace('save', description='"Save This Page" Service')


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
        self.kafka_launcher.launch(url, "save-page-now", webrender_this=True, launch_ts='now', inherit_launch_ts=False)

    @nss.doc(id='save_this_page')
    def get(self, url):
        """
        Save This Page service.

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

