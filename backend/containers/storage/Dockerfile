# NOTE - The version is also needed in the site-packages COPY command below
ARG PY_VERSION=3.10
ARG ALPINE_VERSION=3.15
ARG CONTAINER_REGISTRY=docker.io
ARG PYTHON_BASE_IMAGE_SELECTOR=:${PY_VERSION}

# stage - build
FROM ${CONTAINER_REGISTRY}/opentdf/python-base${PYTHON_BASE_IMAGE_SELECTOR} AS build
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
ENV BUCKET ""

EXPOSE 4050
ENTRYPOINT python3 -m uvicorn --host 0.0.0.0 --port 4050 main:app
