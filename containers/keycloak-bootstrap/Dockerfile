# NOTE - This base image is used here, but it should also really be used in other places such as the e2e test
# NOTE - The version is also needed in the site-packages COPY command below and should be x.x not x.x.x
ARG PY_VERSION=3.10

FROM python:${PY_VERSION}

ENV FLASK_APP=app.py
ENV FLASK_ENV=development
ENV CRYPTOGRAPHY_DONT_BUILD_RUST=1

WORKDIR /project
COPY bootstrap.py /project/bootstrap.py
COPY keycloak_bootstrap.py /project/keycloak_bootstrap.py
COPY entitlements_bootstrap.py /project/entitlements_bootstrap.py
COPY requirements.txt /project/

RUN pip install --upgrade pip && \
    pip install --no-cache-dir --requirement requirements.txt

CMD ["/project/bootstrap.py"]
