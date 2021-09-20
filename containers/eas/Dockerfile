# NOTE - This base image is used here, but it should also really be used in other places such as the e2e test
# NOTE - The version is also needed in the site-packages COPY command below
ARG PY_VERSION=3.9

FROM tdf3.python.base:${PY_VERSION} AS build

# Establish a working directory in the container for tdf3_eas. This directory
# does not exist but will be created. All future commands root from here.

WORKDIR /eas_app
ENV PYTHONPATH .
ENV PYTHONPYCACHEPREFIX /app-pyc
ENV PYTHONUNBUFFERED 1

# NOTE - This must match the GID set for the certs in tools/genkey_apps or the value passed in via docker --user
ENV EAS_UID ${EAS_UID:-908}

# Install apk dependencies
RUN apk add --no-cache --upgrade \
    cargo \
    openssl-dev \
    python3-dev

# Install application into WORKDIR
COPY . /eas_app
RUN pipenv install --dev --system --deploy --ignore-pipfile
# Compile application
RUN python3 -m compileall .

# stage - production server
FROM tdf3.python.base:${PY_VERSION} AS production
ARG PY_VERSION
WORKDIR /eas_app
RUN apk add --no-cache --upgrade \
    bash \
    postgresql-client \
    libressl
ENV EAS_UID ${EAS_UID:-908}
# Install pip dependencies
RUN pip3 install \
    gunicorn==20.0.4 \
    gunicorn[gthread]==20.0.4

# Add eas user and eas group
RUN addgroup -S eas && adduser -S --uid ${EAS_UID:-908} eas -G eas && chown -R eas: /eas_app

COPY --from=build --chown=eas:eas /eas_app/ /eas_app
# NOTE - the python version needs to be specified in the following COPY command:
COPY --from=build --chown=root:root /usr/local/lib/python${PY_VERSION}/site-packages/ /usr/local/lib/python${PY_VERSION}/site-packages
# add any new deployable directories and files from the build stage here
RUN mkdir -p /certs && chown eas /certs && chgrp eas /certs

# Run as eas instead of root
USER eas

# Configure Gunicorn
#
# See docs.gunicorn.org/en/latest/settings.html for options.
# The environment variables are those settings variables, but in uppercase
# prefixed with GUNICORN_ for easier parsing.
ENV GUNICORN_WORKERS 1
ENV GUNICORN_THREADS 1
ENV GUNICORN_WORKER-TMP-DIR /dev/shm
ENV GUNICORN_WORKER-CLASS gthread
ENV GUNICORN_PORT 4010
# Environment variables used for CORS configuration
# See https://github.com/may-day/wsgicors for more info.
ENV WSGI_CORS_HEADERS *
ENV WSGI_CORS_METHODS *
ENV WSGI_CORS_MAX_AGE 180
ENV WSGI_CORS_ORIGIN *

# Show endpoint errors at web endpoints - useful for debugging
ENV SHOW_ENDPOINT_ERRORS true
# Publish stats
ENV STATSD_HOST ""
ENV STATSD_PORT "8125"
# Postgres
ENV POSTGRES_HOST ""
ENV POSTGRES_PORT "5432"
ENV POSTGRES_USER ""
ENV POSTGRES_PASSWORD ""
ENV POSTGRES_DB ""

ENTRYPOINT ./scripts/entrypoint
