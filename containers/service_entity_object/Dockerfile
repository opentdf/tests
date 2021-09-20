# NOTE - The version is also needed in the site-packages COPY command below
ARG PY_VERSION=3.9
ARG ALPINE_VERSION=3.13

# stage - build
FROM virtru/etheria-base-build AS build
WORKDIR /build
# Install application dependencies
COPY Pipfile .
COPY Pipfile.lock .
RUN pipenv lock --keep-outdated --requirements > requirements.txt && \
    pip3 install --no-cache-dir -r requirements.txt
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
# Install pip dependencies
#RUN pip3 install --no-cache-dir \
#    "uvicorn[standard]"
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
# Publish stats
ENV STATSD_HOST ""
ENV STATSD_PORT "8125"
# Postgres
ENV POSTGRES_HOST ""
ENV POSTGRES_PORT "5432"
ENV POSTGRES_USER ""
ENV POSTGRES_PASSWORD ""
ENV POSTGRES_DATABASE ""
ENV POSTGRES_SCHEMA "tdf_entitlement"

EXPOSE 4010
ENTRYPOINT python3 -m uvicorn --host 0.0.0.0 --port 4010 main:app