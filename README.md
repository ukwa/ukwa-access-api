UKWA Access API
===============

This [FastAPI](https://fastapi.tiangolo.com/) application acts as a front-end for our access-time API services.

APIs
----

All APIs are documented using Swagger, and the system includes Swagger UI. e.g. when running in dev mode, you can go to:

    http://localhost:8000/docs

and you'll get a UI that describes the APIs.


### Wayback Resolver

This takes the timestamp and URL of interest, and redirects to the appropriate Wayback instance.

### IIIF Image API for rendering archived web pages

urn:pwid:webarchive.org.uk:1995-04-18T15:56:00Z:page:http://acid.matkelly.com

/iiif/2/dXJuOnB3aWQ6d2ViYXJjaGl2ZS5vcmcudWs6MTk5NS0wNC0xOFQxNTo1NjowMFo6cGFnZTpodHRwOi8vYWNpZC5tYXRrZWxseS5jb20==/0,0,1366,1366/300,/0/default.png


Development & Deployment
------------------------

For development, you can run it (in a suitable `virtualenv`) using:

    $ pip install -f requirements.txt
    $ uvicorn ukwa_api.main:app --reload

For staging/beta/production, it's designed to run under Docker, using `uvicorn` as the runtime engine.
