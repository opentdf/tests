ARG PY_TEST_VERSION=3.8
FROM python:${PY_TEST_VERSION}
RUN apt-get update || : && apt-get install curl jq -y
RUN pip3 install --upgrade pip
# test
WORKDIR /test/
# Install pip dependencies
RUN pip3 install --upgrade pip setuptools pipenv
COPY performance-test/Pipfile .
COPY performance-test/Pipfile.lock .
RUN pipenv install --dev --system --deploy --ignore-pipfile
ENV PYTHONPATH .
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# TODO we should use the base python image and not copy in tools
COPY containers/python_base/tools /tools
# test files
COPY performance-test/*.py .
COPY performance-test/fast-api-client/ .
# install specific version of sdk "==1.0.0"
ARG PY_OSS_VERSION="==1.1.1"
RUN pip3 install tdf3sdk${PY_OSS_VERSION}
RUN pip3 show tdf3sdk
# Use local or remote endpoint
ENV EAS_ENDPOINT http://eas:4010
CMD /tools/wait-for-service "${EAS_ENDPOINT}/healthz?probe=readiness" \
    && /tools/wait-for-service "http://kas:8000/healthz?probe=readiness" \
    && ls -l \
    && python3 main.py \
    && python3 get_time.py
