# docker build -t ct1 -f xtest/Dockerfile . && docker run --net=host ct1
# We need `node` for the test harness and node tests, and python pysdk testing
ARG NODE_VERSION=16
ARG PY_OSS_VERSION=1.1.1

FROM node:${NODE_VERSION}

RUN apt-get update || : && apt-get -y install \
  curl \
  default-jdk \
  jq \
  python3 \
  python3-pip \
  python3-venv
RUN pip3 install --upgrade pip

# test
WORKDIR /wrk
COPY ./tests/containers /wrk
COPY ./scripts /scripts
RUN pip3 install --requirement /wrk/clients/requirements.txt

WORKDIR /wrk/clients
RUN npm install

CMD ["python3", "xtest.py"]
