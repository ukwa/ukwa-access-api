import os
import io

from flask import Flask, redirect, url_for, jsonify, request, send_file, abort
from flask_restplus import Resource, Api, fields
from werkzeug.contrib.cache import FileSystemCache

from access_api.kafka_client import CrawlLogConsumer
from access_api.cdx import lookup_in_cdx
from access_api.screenshots import get_rendered_original_stream

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('APP_SECRET', 'dev-mode-key')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['CACHE_FOLDER'] = os.environ.get('CACHE_FOLDER', '__cache__')
cache = FileSystemCache(os.path.join(app.config['CACHE_FOLDER'], 'request_cache'))

api = Api(app, version='1.0', title='UKWA API (PROTOTYPE)', doc='/apidoc/',
          description='API services for interacting with UKWA content. \
                      This is an early-stage prototype and may be changed without notice.')

ns = api.namespace('access', description='Access operations')


@ns.route('/resolve/<string:timestamp>/<path:url>')
@ns.param('timestamp', 'Target timestamp in 14-digit format, e.g. 20170510120000. If unspecified, will direct to the most recent archived snapshot.', required=True, default='20170510120000')
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


@ns.route('/crawler/recent-activity')
class Crawler(Resource):
    @ns.doc(id='get_recent_activity')
    def get(self):
        """
        Summarise recent crawling activity

        This returns a summary of recent crawling activity.
        """
        stats = self.consumer.get_stats()
        return jsonify(stats)



@ns.route('/screenshot/get-original')
@ns.param('url', 'URL to look up.', required=True, location='args', default ='https://www.bl.uk/')
@ns.param('type', 'The type of screenshot', enum=['screenshot', 'thumbnail'], required=True, location='args', default='screenshot')
class Screenshot(Resource):

    @ns.doc(id='get_rendered_original')
    def get(self):
        """
        Grabs an crawl-time screenshot

        This looks up a screenshot of a page, as it was rendered during the crawl.

        """
        url = request.args.get('url')
        #app.logger.debug("Got URL: %s" % url)
        #
        type = request.args.get('type', 'screenshot')
        #app.logger.debug("Got type: %s" % type)

        # Query URL
        qurl = "%s:%s" % (type, url)

        # Check the cache:
        result = cache.get(qurl)
        if result is not None:
            #app.logger.info("Found in cache: %s" % qurl)
            return send_file(io.BytesIO(result['payload']), mimetype=result['content_type'])

        # Query CDX Server for the item
        (warc_filename, warc_offset, compressed_end_offset) = lookup_in_cdx(qurl)

        # If not found, say so:
        if warc_filename is None:
            abort(404)

        # Grab the payload from the WARC and return it.
        stream, content_type = get_rendered_original_stream(warc_filename,warc_offset, compressed_end_offset)

        # Cache thumbnails:
        if type == 'thumbnail':
            payload = stream.read()
            cache.set(qurl, {'payload': payload, 'content_type': content_type}, timeout=60*60)
            return send_file(io.BytesIO(payload), mimetype=content_type)
        else:
            # Stream screenshots:
            return send_file(stream, mimetype=content_type)


@app.before_first_request
def start_up_kafka_client():
    # Set up the crawl log sampler
    kafka_broker = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    kafka_crawled_topic = os.environ.get('KAFKA_CRAWLED_TOPIC', 'uris.crawled.fc')
    kafka_seek_to_beginning = os.environ.get('KAFKA_SEEK_TO_BEGINNING', False)
    # Note that care needs to be taken us using Group IDs, or different workers see different parts of the logs
    consumer = CrawlLogConsumer(
        kafka_crawled_topic, [kafka_broker], None,
        from_beginning=kafka_seek_to_beginning)
    consumer.start()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

