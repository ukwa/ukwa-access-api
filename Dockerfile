FROM python:3.9

WORKDIR /usr/src/access

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Somewhere to store multi-process metrics for Prometheus:
RUN mkdir /tmp_multiproc

# Pick up API version from a build arg.
# See hooks/build.
ARG API_VERSION=dev
ENV API_VERSION=$API_VERSION

# Override this to mount the service at a prefix, e.g. /api/v1/
ENV SCRIPT_NAME="/api"

# Override the worker count:
ENV WORKERS=2
ENV PROMETHEUS_MULTIPROC_DIR=/tmp_multiproc
ENV LOG_LEVEL=info

# Run command with sh so env vars are substituted:
#CMD ["sh", "-c", "uvicorn ukwa_api.main:app --host 0.0.0.0 --port 8000 --root-path ${ROOT_PATH} --workers ${WORKERS} --forwarded-allow-ips='*' --proxy-headers"]
CMD ["sh", "-c", "gunicorn -k ukwa_api.worker.UkwaApiWorker ukwa_api.main:app --bind 0.0.0.0:8000 --workers ${WORKERS} --forwarded-allow-ips '*' --log-level ${LOG_LEVEL} --access-logfile -"]
