ARG PY_VERSION=3.9

# stage - build
FROM tdf3.python.base:${PY_VERSION} AS build
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
COPY containers/service_attribute_authority/ service_attribute_authority/
COPY containers/service_entitlement/ service_entitlement/
COPY containers/service_entity/ service_entity/
COPY containers/service_entity_object/ service_entity_object/
# Postgres
ENV POSTGRES_HOST ""
ENV POSTGRES_PORT "5432"
ENV POSTGRES_USER ""
ENV POSTGRES_PASSWORD ""
ENV POSTGRES_DATABASE ""
ENV POSTGRES_SCHEMA ""

ENTRYPOINT ./entrypoint.sh
