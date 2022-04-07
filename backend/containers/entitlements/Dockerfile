# Context: opentdf/backend/containers
# NOTE - The version is also needed in the site-packages COPY command below
# Context: opentdf/backend/containers
ARG PY_VERSION=3.10
ARG ALPINE_VERSION=3.15
ARG CONTAINER_REGISTRY=docker.io
ARG PYTHON_BASE_IMAGE_SELECTOR=:${PY_VERSION}

# stage - build
FROM ${CONTAINER_REGISTRY}/opentdf/python-base${PYTHON_BASE_IMAGE_SELECTOR} AS build
WORKDIR /build
# Install application dependencies
COPY entitlements/requirements.txt entitlements/requirements.txt
COPY python_base/requirements.txt python_base/requirements.txt
RUN pip3 install --no-cache-dir --upgrade pip setuptools && \
    pip3 install --no-cache-dir --requirement entitlements/requirements.txt
# Install application into WORKDIR
COPY python_base/*.py python_base/
COPY entitlements/*.py entitlements/
COPY entitlements/VERSION entitlements/
COPY entitlements/tests entitlements/tests

# Compile application
RUN python3 -m compileall .

# Validate openapi
COPY entitlements/openapi.json entitlements/
RUN diff <(python3 -m entitlements.main) entitlements/openapi.json

# stage - production server
FROM python:${PY_VERSION}-alpine${ALPINE_VERSION} AS production
ARG PY_VERSION

WORKDIR /app
COPY --from=build --chown=root:root /build/ .
# NOTE - the python version needs to be specified in the following COPY command:
COPY --from=build --chown=root:root /usr/local/lib/python${PY_VERSION}/site-packages/ /usr/local/lib/python${PY_VERSION}/site-packages
# add any new deployable directories and files from the build stage here

# Server
ENV SERVER_ROOT_PATH "/"
ENV SERVER_PORT "4030"
ENV SERVER_PUBLIC_NAME ""
ENV SERVER_LOG_LEVEL "INFO"
ENV SERVER_CORS_ORIGINS ""
# Postgres
ENV POSTGRES_HOST ""
ENV POSTGRES_PORT "5432"
ENV POSTGRES_USER "tdf_entitlement_manager"
ENV POSTGRES_PASSWORD ""
ENV POSTGRES_DATABASE "tdf_database"
ENV POSTGRES_SCHEMA "tdf_entitlement"
# OIDC
ENV OIDC_CLIENT_ID ""
ENV OIDC_CLIENT_SECRET ""
ENV OIDC_REALM ""
## trailing / is required
ENV OIDC_SERVER_URL ""
ENV OIDC_AUTHORIZATION_URL ""
ENV OIDC_TOKEN_URL ""
# Disable OpenAPI
ENV OPENAPI_URL ""

ENTRYPOINT python3 -m uvicorn \
    --host 0.0.0.0 \
    --port ${SERVER_PORT} \
    --root-path ${SERVER_ROOT_PATH} \
    --no-use-colors \
    --no-server-header \
    --log-level error \
    entitlements.main:app
