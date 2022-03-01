ARG PY_VERSION=3.10
ARG CONTAINER_REGISTRY=docker.io
ARG PYTHON_BASE_IMAGE_SELECTOR=:${PY_VERSION}

# stage - build
FROM ${CONTAINER_REGISTRY}/opentdf/python-base${PYTHON_BASE_IMAGE_SELECTOR} AS build
WORKDIR /tool
# Install tool dependencies
COPY containers/migration/Pipfile .
COPY containers/migration/Pipfile.lock .
RUN pipenv lock --keep-outdated --requirements > requirements.txt && \
    pip3 install --no-cache-dir -r requirements.txt
# Install tool into WORKDIR
COPY alembic.ini .
COPY containers/migration/entrypoint.sh .
COPY containers/migration/ migration/
RUN mkdir -p /tool/migration/versions
COPY containers/attributes/ attributes/
COPY containers/entitlements/ entitlements/
COPY containers/service_entity/ service_entity/
COPY containers/claims/ claims/
# Postgres
ENV POSTGRES_HOST ""
ENV POSTGRES_PORT "5432"
ENV POSTGRES_USER ""
ENV POSTGRES_PASSWORD ""
ENV POSTGRES_DATABASE ""
ENV POSTGRES_SCHEMA ""

ENTRYPOINT ./entrypoint.sh
