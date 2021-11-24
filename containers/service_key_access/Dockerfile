# NOTE - The version is also needed in the site-packages COPY command below
ARG PY_VERSION=3.9
ARG ALPINE_VERSION=3.13

# stage - build
FROM virtru/tdf-python-base:${PY_VERSION} AS build
WORKDIR /build
# Install application dependencies
COPY service_key_access/Pipfile .
COPY service_key_access/Pipfile.lock .
RUN pipenv lock --keep-outdated --requirements > requirements.txt && \
    pip3 install --no-cache-dir -r requirements.txt
# Install application into WORKDIR
COPY service_key_access/main.py .
RUN ls -la
COPY service_key_access/tdf3_kas_core/ ./tdf3_kas_core/
# Compile application
RUN python3 -m compileall .
# stage - production server
FROM python:${PY_VERSION}-alpine${ALPINE_VERSION} AS production
ARG PY_VERSION
# Install apk dependencies
RUN apk add --no-cache --upgrade \
    bash \
    libressl
WORKDIR /app
COPY --from=build --chown=root:root /build/ .
# NOTE - the python version needs to be specified in the following COPY command:
COPY --from=build --chown=root:root /usr/local/lib/python${PY_VERSION}/site-packages/ /usr/local/lib/python${PY_VERSION}/site-packages
# add any new deployable directories and files from the build stage here

# Application
ENV KAS_PRIVATE_KEY ""
ENV KAS_EC_SECP256R1_PRIVATE_KEY ""
ENV KAS_EC_SECP256R1_CERTIFICATE ""
ENV KAS_PRIVATE_KEY ""
ENV KAS_CERTIFICATE ""
ENV EAS_HOST ""
ENV EAS_CERTIFICATE ""
# Publish stats
ENV STATSD_HOST ""
ENV STATSD_PORT "8125"

EXPOSE 8000
ENTRYPOINT python3 -m uvicorn --host 0.0.0.0 --port 8000 main:app