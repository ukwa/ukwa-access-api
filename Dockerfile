FROM python:3.9

WORKDIR /usr/src/access

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pick up API version from a build arg.
# See hooks/build.
ARG API_VERSION=dev
ENV API_VERSION=$API_VERSION

# Override this to mount the service at a prefix, e.g. /api/v1/
ENV ROOT_PATH="/api"

# Override the worker count:
ENV WORKERS=2

# Run command with sh so env vars are substituted:
CMD ["sh", "-c", "uvicorn ukwa_api.main:app --host 0.0.0.0 --port 8000 --root-path ${ROOT_PATH} --workers ${WORKERS} --proxy-headers"]


