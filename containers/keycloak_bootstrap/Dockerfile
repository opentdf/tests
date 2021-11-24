# NOTE - This base image is used here, but it should also really be used in other places such as the e2e test
# NOTE - The version is also needed in the site-packages COPY command below and should be x.x not x.x.x
ARG PY_VERSION=3.9
ARG ALPINE_VERSION=3.13

FROM python:${PY_VERSION}-alpine${ALPINE_VERSION}

ENV FLASK_APP=app.py
ENV FLASK_ENV=development
ENV CRYPTOGRAPHY_DONT_BUILD_RUST=1

WORKDIR /project
COPY bootstrap.py /project/bootstrap.py
COPY Makefile /project/Makefile
COPY Pipfile /project/Pipfile
COPY Pipfile.lock /project/Pipfile.lock
COPY .pylintrc /project/.pylintrc
COPY test_bootstrap.py /project/test_bootstrap.py

RUN apk --no-cache --virtual build-dependencies add \
    make && \
    apk add --update gcc \
    libffi-dev \
    musl-dev \
    openssl-dev \
    python3-dev \
    curl \
    py-pip \
    py-setuptools && \
    pip3 install pipenv && \
    pip install --upgrade pip && \
    make dockertestenv localbuild

CMD ["/project/.venv/bin/python3","bootstrap.py"]
