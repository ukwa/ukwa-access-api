UKWA Access API
===============

This [Flask RESTPlus](https://flask-restplus.readthedocs.io/) application acts as a front-end for our access-time API services.

APIs
----

Currently, it provides the ARK and URL resolution services.

### ARK Resolver

This looks up ARKs in a simple text file. See [api-data/arks.txt](api-data/arks.txt) for an example.

    <ARK> <TIMESTAMP> <URL>

It just maps an ARK to a timestamp and URL, which is then passed to the Wayback Resolver.

The file should be generated from W3ACT in a separate process, see python-shepherd for details.

### Wayback Resolver

This takes the timestamp and URL of interest, and redirects to the appropriate Wayback instance.


Development & Deployment
------------------------

For development, you can run it (in a suitable `virtualenv`) using:

    $ pip install -f requirements.txt
    $ python api.py

For testing/production, it's designed to run under Docker, using `gunicorn` as the runtime engine.
