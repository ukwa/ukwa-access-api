from flask import Flask, redirect
from flask_restplus import Resource, Api

app = Flask(__name__)
api = Api(app, version='1.0', title='UKWA API', description='API services for interacting with UKWA content.')

ns = api.namespace('access', description='Access operations')

@ns.route('/resolve/<string:ts>/<path:url>')
@ns.param('ts', 'Target timestamp in 14-digit format, e.g. 20170510120000. If unspecified, will direct to the most recent archived snapshot.', required=True)
@ns.param('url', 'URL to look up.', required=True)
class WaybackResolver(Resource):
    '''Redirects the incoming request to the most suitable archived version of a given URL.'''
    @ns.doc(id='get_wayback_resolver')
    @ns.response(307, 'Redirects the incoming request to the most suitable representation of the URL. If the client is in a reading room, they will be redirected to their local acces gateway. If the client is off-site, they will be redirected to the Open UK Web Archive.')
    def get(self, ts, url):
        return redirect('https://www.webarchive.org.uk/wayback/archive/%s/%s' % (ts, url), code=307)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

