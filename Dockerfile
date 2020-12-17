FROM python:3.8

WORKDIR /usr/src/access

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pick up API version from the DOCKER_TAG
# https://docs.docker.com/docker-hub/builds/advanced/#environment-variables-for-building-and-testing
ARG API_VERSION=${DOCKER_TAG}

CMD gunicorn -c gunicorn.ini api:app


