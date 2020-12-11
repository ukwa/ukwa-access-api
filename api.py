import os
import io
import re
import json
import requests
from urllib.parse import quote
from base64 import b64decode

from flask import Flask, redirect, url_for, jsonify, request, send_file, abort, render_template, Response
from flask_restx import Resource, Api, fields
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
app.wsgi_app = ProxyFix(app.wsgi_app, x_host=1, x_port=1, x_prefix=1) # For https://stackoverflow.com/questions/23347387/x-forwarded-proto-and-flask X-Forwarded-Proto
app.config['SECRET_KEY'] = os.environ.get('APP_SECRET', 'dev-mode-key')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['CACHE_FOLDER'] = os.environ.get('CACHE_FOLDER', '__cache__')

# Set up a persistent cache for screenshots etc.
screenshot_cache = FileSystemCache(os.path.join(app.config['CACHE_FOLDER'], 'screenshot_cache'), threshold=0, default_timeout=0)

# Get the Wayback endpoint to check for access rights:
WAYBACK_SERVER = os.environ.get("WAYBACK_SERVER", "https://www.webarchive.org.uk/wayback/archive/")

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

# Patch the API so it's visible on HTTPS/HTTP
class PatchedApi(Api):
    @property
    def specs_url(self):
        if 'HTTP_X_FORWARDED_PROTO' in os.environ:
            return url_for(self.endpoint('specs'), _external=True, _scheme=os.environ['HTTP_X_FORWARDED_PROTO'])
        else:
            return url_for(self.endpoint('specs'), _external=True)

# Set up the API base:
api = PatchedApi(app, version=API_VERSION, title=API_LABEL, doc=None,
          description='API services for the UK Web Archive.<br/> \
                      <b>This is an early-stage prototype and may be changed without notice.</b>')

app.config.PREFERRED_URL_SCHEME = 'https'

class RenderedPageSchema(fields.Raw):
    __schema_type__ = 'file'
    __schema_format__ = 'A rendered version of the given URL.'

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
@ns.param('url', 'URL to find.', required=True)
@ns.param('timestamp', 'Target timestamp in 14-digit format, e.g. `20170510120000`. If unspecified, will direct to the most recent archived snapshot.',
          required=True)
class WaybackResolver(Resource):
    @ns.doc(id='get_wayback_resolver')
    @ns.response(307, 'Redirects the incoming request to the most suitable representation of the URL. If the client is in a reading room, they will be redirected to their local acces gateway. If the client is off-site, they will be redirected to the Open UK Web Archive.')
    def get(self, timestamp, url):
        """
        Resolve a timestamp and URL
        
        Redirects the incoming request to the most suitable archived version of a given URL, closest to the given timestamp. 
        Currently redirects to the open access part of the UK Web Archive only.

        """
        return redirect('/wayback/archive/%s/%s' % (timestamp, url), code=307)

@ns.route('/lookup')
@ns.param('sort', 'Order to return results.', enum=[ "default", "closest", "reverse"  ],
          required=False, location='args', default='default')
@ns.param('matchType', 'Type of match to look for.', enum=[ "exact", "prefix", "host", "domain", "range" ],
          required=False, location='args', default='exact')
@ns.param('url', 'URL to look for (will canonicalize the URL before running the query).', required=True, location='args',
          default='http://portico.bl.uk/')
class CDXServer(Resource):
    @ns.doc(id='get_cdx_server')
    @ns.produces(['text/plain'])
    @ns.response(200, 'A list of matches in [11-field CDX format](https://iipc.github.io/warc-specifications/specifications/cdx-format/cdx-2015/).')
    def get(self):
        """
        Lookup a URL

        Queries our main index for URLs via the <a href="https://github.com/webrecorder/pywb/wiki/CDX-Server-API">CDX API</a>, as implemented by <a href="https://github.com/nla/outbackcdx">OutbackCDX</a>.
        
        Note that our <a href="/wayback/archive/">Wayback service</a> also supports the Memento API as per https://tools.ietf.org/html/rfc7089

        """
        # Only put through allowed parameters:
        params = {
            'url': request.args.get('url'),
            'matchType': request.args.get('matchType', 'exact'),
            'sort': request.args.get('sort', 'default')
        }
        # Open a streaming call to cdx.api.wa.bl.uk/data-heritrix and stream the results back...
        r = requests.request(
            method='GET',
            url=f"{CDX_SERVER}",
            params=params,
            stream=True
            )
        return Response(r.iter_content(chunk_size=10*1024),
                    content_type=r.headers['Content-Type'])


# ----------
# IIIF API
# ----------
nsr = api.namespace('IIIF', path="/iiif", description='Access screenshots of archived websites via the <a href="https://iiif.io/api/">IIIF</a> <a href="https://iiif.io/api/image/2.1/">Image API 2.1</a>')
@nsr.route('/2/<path:pwid>/<string:region>/<string:size>/<int:rotation>/<string:quality>.<string:format>')
@nsr.param('format', 'IIIF image request <a href="https://iiif.io/api/image/2.1/#format">format</a>.', required=True, default='png', enum=['png','jpg'])
@nsr.param('quality', 'IIIF image request <a href="https://iiif.io/api/image/2.1/#quality">quality</a>.', required=True, default='default', enum=['default', 'grey'])
@nsr.param('rotation', 'IIIF image request <a href="https://iiif.io/api/image/2.1/#rotation">rotation (degrees)</a>.', required=True, default='0')
@nsr.param('size', 'IIIF image request <a href="https://iiif.io/api/image/2.1/#size">size</a>.', required=True, default='full')
@nsr.param('region', 'IIIF image request <a href="https://iiif.io/api/image/2.1/#region">region</a>.', required=True, default='full')
@nsr.param('pwid', 'A <a href="https://tools.ietf.org/html/draft-pwid-urn-specification-09">Persistent Web IDentifier (PWID) URN</a>. The identifier must be URL-encoded or Base64 encoded UTF-8 text. <br/>For example, the pwid <br/>`urn:pwid:webarchive.org.uk:1995-04-18T15:56:00Z:page:http://portico.bl.uk/`<br/> must be encoded as: <br/><tt>urn%253Apwid%253Awebarchive.org.uk%253A1995-04-18T15%253A56%253A00Z%253Apage%253Ahttp%253A%252F%252Fportico.bl.uk%252F</tt><br/> or in Base64 as: <br>`dXJuOnB3aWQ6d2ViYXJjaGl2ZS5vcmcudWs6MTk5NS0wNC0xOFQxNTo1NjowMFo6cGFnZTpodHRwOi8vcG9ydGljby5ibC51ay8=`',
          required=True)
class IIIFRenderer(Resource):
    @nsr.doc(id='iiif_2', model=RenderedPageSchema)
    @nsr.produces(['image/png', 'image/jpeg'])
    @nsr.response(200, 'The requested image, if available.')
    def get(self, pwid, region, size, rotation, quality, format):
        """
        IIIF images of archived web pages.

        Access images of rendered archived web pages via the <a href="https://iiif.io/api/">IIIF</a> <a href="https://iiif.io/api/image/2.1/">Image API 2.1</a>.
        """
 
        app.logger.info("IIIF PWID: %s" % pwid)

        # Re-encode the PWID for passing on:
        pwid_encoded = quote(pwid, safe='')

        # Proxy requests to IIIF server:
        resp = requests.request(
            method='GET',
            url=f"{IIIF_SERVER}/iiif/2/{pwid_encoded}/{region}/{size}/{rotation}/{quality}.{format}",
            headers={key: value for (key, value) in request.headers if key != 'Host'}
            )

        headers = [(name, value) for (name, value) in resp.raw.headers.items()]

        response = Response(resp.content, resp.status_code, headers)
        return response

@nsr.route('/2/<path:pwid>/info.json')
@nsr.param('pwid', 'A <a href="https://tools.ietf.org/html/draft-pwid-urn-specification-09">Persistent Web IDentifier (PWID) URN</a>. The identifier must be URL-encoded or Base64 encoded UTF-8 text. <br/>For example, the pwid <br/>`urn:pwid:webarchive.org.uk:1995-04-18T15:56:00Z:page:http://portico.bl.uk/`<br/> must be encoded as: <br/><tt>urn%253Apwid%253Awebarchive.org.uk%253A1995-04-18T15%253A56%253A00Z%253Apage%253Ahttp%253A%252F%252Fportico.bl.uk%252F</tt><br/> or in Base64 as: <br>`dXJuOnB3aWQ6d2ViYXJjaGl2ZS5vcmcudWs6MTk5NS0wNC0xOFQxNTo1NjowMFo6cGFnZTpodHRwOi8vcG9ydGljby5ibC51ay8=`',
          required=True)
class IIIFInfo(Resource):
    @nsr.doc(id='iiif_2_info')
    @nsr.produces(['application/json'])
    @nsr.response(200, 'The info.json for this image')
    def get(self, pwid):
        """
        IIIF Image information
        """
 
        app.logger.info("IIIF PWID: %s" % pwid)

        # Re-encode the PWID for passing on:
        pwid_encoded = quote(pwid, safe='')

        # Proxy requests to IIIF server:
        resp = requests.request(
            method='GET',
            url=f"{IIIF_SERVER}/iiif/2/{pwid_encoded}/info.json",
            headers={key: value for (key, value) in request.headers if key != 'Host'}
            )

        headers = [(name, value) for (name, value) in resp.raw.headers.items()]

        response = Response(resp.content, resp.status_code, headers)
        return response

@nsr.route('/helper/<string:timestamp>/<path:url>')
@nsr.param('url', 'URL to render.', required=True)
@nsr.param('timestamp', 'Target timestamp in 14-digit format, e.g. `20170510120000`. If unspecified, will direct to the most recent archived snapshot.',
          required=True)
class IIIFHelper(Resource):
    @nsr.doc(id='iiif_helper_pwid')
    @nsr.response(307, 'Redirects to an IIIF URL.')
    def get(self, timestamp, url):
        """
        
        Generate an IIIF URL
        
        Redirect to a suitable IIIF URL using a PWID with the given timestamp and url properly encoded. 
        
        """
        pwid = gen_pwid(timestamp,quote(url,safe=''))
        nurl = url_for('IIIF_iiif_renderer', pwid=pwid, region='0,0,1024,1024', size='600,', rotation=0, quality='default', format='png')
        return redirect(nurl, code=303)


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
    @nss.produces(['application/json'])
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

@app.route('/render_raw', methods=['HEAD', 'GET'])
def render_raw():
    """
    Grabs an screenshot of an web page.

    This looks for a screenshot of a web page, returning the most recent archived version by default.

    If the <tt>source</tt> is set to <tt>original</tt> the system will \
    attempt to fine a screenshot of the original web site, as seen at crawl time. If the <tt>source</tt> is set to \
    <tt>archive</tt> then a rendering of the archived version of the page will be returned instead.

    All seeds should have a <tt>screenshot</tt> - the other rendered types are usually present with the exception of 'pdf' which is under development.

    Caching should be done downstream, but some caching is done here as the current IIIF server seems to fetch twice.

    """

    url = request.args.get('url', None)
    pwid = request.args.get('pwid', None)
    type = request.args.get('type', 'screenshot')
    source = request.args.get('source', 'archive')
    target_date = request.args.get('target_date', None)

    # Must have url or pwid:
    if not url and not pwid:
        abort(Response('Must specify URL or PWID', status=400))

    if pwid:
        # Decode Base64 if needed
        if not pwid.startswith('urn:pwid:'):
            # Attempt to decode Base64
            try:
                decodedbytes = b64decode(pwid)
                decoded = decodedbytes.decode("utf-8") 
            except Exception as e:
                app.logger.exception("Failed to decode", e)
                decoded = ""
            # And check the result:
            if decoded.startswith('urn:pwid:'):
                pwid = decoded
            else:
                abort(Response(f'Could not decode PWID {pwid}', status=400))

        # Parse the PWID
        # urn:pwid:webarchive.org.uk:1995-04-18T15:56:00Z:page:http://portico.bl.uk/    
        m = re.compile('^urn:pwid:([^:]+):([^Z]+Z):([^:]+):(.+)$')
        parts = m.match(pwid)
        if not parts or len(parts.groups()) != 4:
            abort(Response(f'Could not parse PWID {pwid}', status=400))

        # Not all archives...
        if parts.group(1) != 'webarchive.org.uk':
            abort(Response(f'Only webarchive.org.uk PWIDs are supported.', status=400))

        # Not all scopes...
        if parts.group(3) != 'page':
            abort(Response(f'Only page PWIDs are supported.', status=400))

        # Continue with all that is good:
        url = parts.group(4)
        # Convert https to http as the screenshotter doesn't like it with pywb it seems:
        if url.startswith('https:'):
            url = url.replace('https', 'http', 1)
        target_date = re.sub('[^0-9]','', parts.group(2))

        # First check with a Wayback service to see if this URL is allowed:
        # This defaults to the public OA service, to avoid accidentally making non-OA material available.
        r = requests.get("%s%s" %(WAYBACK_SERVER, url))
        if r.status_code < 200 or r.status_code >= 400:
            abort(Response(r.reason, status=r.status_code))

    # Rebuild the PWID:
    pwid = gen_pwid(target_date, url)
    app.logger.info("Got PWID: %s" % pwid)

    # Request is okay in principle, so return 200 if this is a HEAD request:
    if request.method == 'HEAD':
        return jsonify(pwid=pwid, success=True)

    # Use cached value if there is one, using pwid as key:
    result = screenshot_cache.get(pwid)
    if result is not None:
        #app.logger.info("Found in cache: %s" % pwid)
        return send_file(io.BytesIO(result['payload']), mimetype=result['content_type'])
    

    # For originals:
    if source == 'original':
        # Query CDX Server for the item
        qurl = "%s:%s" % (type, url)
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
    image_file = stream.read()
    screenshot_cache.set(pwid, {'payload': image_file, 'content_type': content_type}, timeout=60*60)
    return send_file(io.BytesIO(image_file), mimetype=content_type)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

