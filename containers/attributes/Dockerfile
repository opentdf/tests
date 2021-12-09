# NOTE - The version is also needed in the site-packages COPY command below
ARG PY_VERSION=3.9
ARG ALPINE_VERSION=3.13

# stage - build
FROM virtru/tdf-python-base:${PY_VERSION} AS build
WORKDIR /build
# Install application dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir --requirement requirements.txt
# Install application into WORKDIR
COPY main.py .
# Compile application
RUN python3 -m compileall .

# stage - production server
FROM python:${PY_VERSION}-alpine${ALPINE_VERSION} AS production
ARG PY_VERSION
# Install apk dependencies
RUN apk add --no-cache --upgrade \
    bash \
    postgresql-client \
    libressl
WORKDIR /app
COPY --from=build --chown=root:root /build/ .
# NOTE - the python version needs to be specified in the following COPY command:
COPY --from=build --chown=root:root /usr/local/lib/python${PY_VERSION}/site-packages/ /usr/local/lib/python${PY_VERSION}/site-packages
# add any new deployable directories and files from the build stage here

# Server
ENV SERVER_ROOT_PATH "/"
ENV SERVER_PORT "4020"
ENV SERVER_PUBLIC_NAME ""
ENV SERVER_LOG_LEVEL "INFO"
# Postgres
ENV POSTGRES_HOST ""
ENV POSTGRES_PORT "5432"
ENV POSTGRES_USER ""
ENV POSTGRES_PASSWORD ""
ENV POSTGRES_DATABASE ""
ENV POSTGRES_SCHEMA "tdf_attribute"
# OIDC
ENV OIDC_CLIENT_ID ""
ENV OIDC_CLIENT_SECRET ""
ENV OIDC_REALM ""
## trailing / is required
ENV OIDC_SERVER_URL ""
ENV OIDC_AUTHORIZATION_URL ""
ENV OIDC_TOKEN_URL ""
ENV OIDC_CONFIGURATION_URL ""
# Disable OpenAPI
ENV OPENAPI_URL ""

ENTRYPOINT python3 -m uvicorn \
    --host 0.0.0.0 \
    --port ${SERVER_PORT} \
    --root-path ${SERVER_ROOT_PATH} \
    --no-use-colors \
    --no-server-header \
    --log-level error \
    main:app