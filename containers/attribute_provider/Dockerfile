# NOTE - This base image is used here, but it should also really be used in other places such as the e2e test
# NOTE - The version is also needed in the site-packages COPY command below and should be x.x not x.x.x
ARG PY_VERSION=3.9

FROM tdf3.python.base:${PY_VERSION}

ENV FLASK_APP=src/attribute_provider/app.py
ENV FLASK_ENV=development
ENV PIPENV_VENV_IN_PROJECT=enabled

WORKDIR /project
COPY Makefile /project
COPY Pipfile /project
COPY Pipfile.lock /project
COPY README.md /project
COPY pyproject.toml /project
COPY setup.cfg /project
COPY setup.py /project
COPY src /project/src
COPY tests /project/tests

RUN apk --no-cache --virtual build-dependencies add \
	make python3-dev && \
	pip3 install pipenv && \
    make dockertestenv localbuild

EXPOSE 5000
CMD ["/project/.venv/bin/flask","run","--host","0.0.0.0"]
