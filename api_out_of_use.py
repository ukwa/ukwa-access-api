from flask import Flask, redirect, url_for
from flask_restplus import Resource, Api

app = Flask(__name__)
api = Api(app, version='1.0', title='UKWA API', description='API services for interacting with UKWA content. (PROTOTYPE)')

ns = api.namespace('access', description='Access operations')


@ns.route('/resolve/ark:/<int:ark_naan>/<string:ark_name>')
@ns.param('ark_naan', "The Name Assigning Authority Number part of the ARK (81055 for BL).", required=True, default='81055')
@ns.param('ark_name', "The 'name' part of the ARK, e.g. vdc_10022556865.0x000001", required=True)
class ArkResolver(Resource):
    '''Looks up the ARK and Redirects the incoming request to the most suitable archived version of that resource.'''
    @ns.doc(id='get_ark_resolver')
    @ns.response(307, 'Redirects the incoming request to the most suitable archived web page identifer that acts as the representation of the ARK.')
    @ns.response(404, 'ARK is not known to this system.')
    def get(self, ark_naan, ark_name):
        with open('./api-data/arks.txt') as f:
            for line in f.readlines():
                ark, ts, url = line.strip().split(' ', maxsplit=2)
                if ark_name in ark:
                    return redirect(url_for( 'access_wayback_resolver', timestamp=ts, url=url), code=307)
        # No match:
        api.abort(404, 'No matching ARK found!')


@ns.route('/resolve/<string:timestamp>/<path:url>')
@ns.param('timestamp', 'Target timestamp in 14-digit format, e.g. 20170510120000. If unspecified, will direct to the most recent archived snapshot.', required=True, example='20170510120000')
@ns.param('url', 'URL to look up.', required=True, example='https://www.bl.uk/')
class WaybackResolver(Resource):
    '''Redirects the incoming request to the most suitable archived version of a given URL.'''
    @ns.doc(id='get_wayback_resolver')
    @ns.response(307, 'Redirects the incoming request to the most suitable representation of the URL. If the client is in a reading room, they will be redirected to their local acces gateway. If the client is off-site, they will be redirected to the Open UK Web Archive.')
    def get(self, timestamp, url):
        return redirect('https://www.webarchive.org.uk/wayback/archive/%s/%s' % (timestamp, url), code=307)


@app.route('/activity/json')
def get_recent_activity_json():
    stats = consumer.get_stats()
    return jsonify(stats)


@app.route('/get-rendered-original')
def get_rendered_original():
    """
    Grabs a rendered resource.

    Only reason Wayback can't do this is that it does not like the extended URIs
    i.e. 'screenshot:http://' and replaces them with 'http://screenshot:http://'
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

