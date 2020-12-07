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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

