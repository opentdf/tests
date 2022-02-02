# Context: opentdf/backend/containers
# NOTE - The version is also needed in the site-packages COPY command below
# context must be parent folder
ARG PY_VERSION=3.10
ARG ALPINE_VERSION=3.15
ARG CONTAINER_REGISTRY=docker.io
ARG PYTHON_BASE_IMAGE_SELECTOR=:${PY_VERSION}

# stage - build
FROM ${CONTAINER_REGISTRY}/opentdf/python-base${PYTHON_BASE_IMAGE_SELECTOR} AS build
WORKDIR /build
# Install application dependencies
COPY claims/requirements.txt claims/requirements.txt
COPY python_base/requirements.txt python_base/requirements.txt
RUN pip3 install --no-cache-dir --upgrade pip setuptools && \
    pip3 install --no-cache-dir --requirement claims/requirements.txt
# Install application into WORKDIR
COPY python_base/*.py python_base/
COPY claims/*.py claims/

# Compile application
RUN python3 -m compileall .

# stage - production server
FROM python:${PY_VERSION}-alpine${ALPINE_VERSION} AS production
ARG PY_VERSION

WORKDIR /app
COPY --from=build --chown=root:root /build/ .
# NOTE - the python version needs to be specified in the following COPY command:
COPY --from=build --chown=root:root /usr/local/lib/python${PY_VERSION}/site-packages/ /usr/local/lib/python${PY_VERSION}/site-packages
# add any new deployable directories and files from the build stage here

# Application
ENV EAS_PRIVATE_KEY ""
ENV EAS_ENTITY_EXPIRATION ""
ENV KAS_DEFAULT_URL ""
ENV KAS_CERTIFICATE ""
ENV KAS_EC_SECP256R1_CERTIFICATE ""
# Server
ENV SERVER_ROOT_PATH "/"
ENV SERVER_PORT "5000"
ENV SERVER_PUBLIC_NAME ""
ENV SERVER_LOG_LEVEL "INFO"
# Postgres
ENV POSTGRES_HOST ""
ENV POSTGRES_PORT "5432"
ENV POSTGRES_USER ""
ENV POSTGRES_PASSWORD ""
ENV POSTGRES_DATABASE ""
ENV POSTGRES_SCHEMA "tdf_entitlement"

EXPOSE 5000
ENTRYPOINT python3 -m uvicorn \
    --host 0.0.0.0 \
    --port ${SERVER_PORT} \
    --root-path ${SERVER_ROOT_PATH} \
    --no-use-colors \
    --no-server-header \
    --log-level error \
    claims.main:app
