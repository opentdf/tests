ARG PY_VERSION=3.9
FROM python:${PY_VERSION}

# Set up the environment
WORKDIR /usr/tdf3_kas_core
ENV PYTHONPATH .
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Get and install the local folder
COPY . .
RUN pip3 install .

# install the test tools
RUN pip3 install pytest pytest-cov

# run the test
CMD ["pytest"]
