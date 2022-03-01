# docker build -t ct1 -f xtest/clients/Dockerfile . && docker run --net=host ct1
# We need `node` for the test harness and node tests, and python pysdk testing
ARG NODE_VERSION=16
ARG PY_OSS_VERSION=1.1.1
ARG PY_TEST_VERSION=3.8

FROM node:${NODE_VERSION}


RUN apt-get update || : && apt-get -y install \
  curl \
  default-jdk \
  jq \
  python:${PY_TEST_VERSION} \
  python3-pip \
  python3-venv
RUN pip3 install --upgrade pip
RUN python3 --version

# test
WORKDIR /wrk
COPY ./xtest/clients /wrk
RUN npm install

RUN pip3 install --requirement /wrk/requirements.txt

CMD ["python3", "xtest.py"]
