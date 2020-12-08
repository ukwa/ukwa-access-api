UKWA Access API
===============

This [Flask RESTPlus](https://flask-restplus.readthedocs.io/) application acts as a front-end for our access-time API services.

APIs
----

All APIs are documented using Swagger, and the system includes Swagger UI. e.g. when running in dev mode, you can go to:

    http://localhost:5000/

and you'll get a UI that describes the APIs. (This may not be directly visible in production, i.e. when running behind a proxy.)

Currently, it provides the ARK and URL resolution services.

### ARK Resolver

This looks up ARKs in a simple text file. See [api-data/arks.txt](api-data/arks.txt) for an example.

    <ARK> <TIMESTAMP> <URL>

It just maps an ARK to a timestamp and URL, which is then passed to the Wayback Resolver.

The file should be generated from W3ACT in a separate process, see python-shepherd for details.

### Wayback Resolver

This takes the timestamp and URL of interest, and redirects to the appropriate Wayback instance.

### IIIF Image API for rendering archived web pages

urn:pwid:webarchive.org.uk:1995-04-18T15:56:00Z:page:http://acid.matkelly.com

/iiif/2/dXJuOnB3aWQ6d2ViYXJjaGl2ZS5vcmcudWs6MTk5NS0wNC0xOFQxNTo1NjowMFo6cGFnZTpodHRwOi8vYWNpZC5tYXRrZWxseS5jb20==/0,0,1366,1366/300,/0/default.png


Development & Deployment
------------------------

For development, you can run it (in a suitable `virtualenv`) using:

    $ pip install -f requirements.txt
    $ python api.py

For testing/production, it's designed to run under Docker, using `gunicorn` as the runtime engine.
