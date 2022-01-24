ARG PY_VERSION=3.10
ARG ALPINE_VERSION=3.15

# stage - build
FROM python:${PY_VERSION}-alpine${ALPINE_VERSION} AS build
# Install apk dependencies
RUN apk add --no-cache --upgrade \
    gcc \
    rust \
    build-base \
    postgresql-dev \
    postgresql-client \
    libressl-dev \
    musl-dev \
    zlib-dev \
    jpeg-dev \
    libffi-dev \
    openssl \
    bash

COPY ./scripts /scripts

WORKDIR /build
# Install pip dependencies
ENV CRYPTOGRAPHY_DONT_BUILD_RUST=1
COPY requirements.txt .
RUN pip3 install --no-cache-dir --upgrade pip setuptools pipenv && \
    pip3 install --no-cache-dir -r requirements.txt
