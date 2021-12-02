ARG NODE_VERSION=lts
ARG PY_OSS_VERSION=1.1.1
FROM node:${NODE_VERSION}
#Why is this a node base? Why not Py(thon)?

# docker build -t ct1 -f xtest/Dockerfile . && docker run --net=host ct1
# We need `node` for the test harness and node tests, and python pysdk testing

RUN apt-get update || : && apt-get -y install \
  curl \
  default-jdk \
  jq \
  python3 \
  python3-pip \
  python3-venv
RUN pip3 install --upgrade pip

# test
WORKDIR /xtest
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
COPY ./xtest /xtest
COPY ./containers/python_base/scripts /scripts
RUN pip3 install --requirement /xtest/requirements.txt
# install specific version of sdk "==1.0.0"
RUN pip3 install tdf3sdk${PY_OSS_VERSION}
RUN pip3 show tdf3sdk
# run test
CMD ["/xtest/scripts/wait-and-test", "/xtest/config-oss.json", "--stage", "local", "--sdks", "sdk/py/oss/cli.sh"]
