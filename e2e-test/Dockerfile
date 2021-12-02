ARG PY_TEST_VERSION=3.8
FROM python:${PY_TEST_VERSION}
RUN apt-get update || : && apt-get install --no-install-recommends --yes \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get purge --auto-remove \
    && apt-get clean
RUN pip3 install --no-cache-dir --upgrade pip
# test
WORKDIR /test/
COPY e2e-test/requirements.txt ./
RUN pip3 install --no-cache-dir --requirement requirements.txt
# tool files
COPY containers/python_base/scripts /scripts
# test files
COPY e2e-test/*.py ./
COPY e2e-test/resources/ resources/
# install specific version of sdk "==1.0.0"
ARG PY_OSS_VERSION
RUN pip3 install --no-cache-dir tdf3sdk${PY_OSS_VERSION}
# Use local or remote endpoint
ENV KAS_HOST http://kas:8000
ENV ENTITY_OBJECT_HOST http://eas:4010
ENV ATTRIBUTE_AUTHORITY_HOST http://attributes:4020
ENV ENTITLEMENT_HOST http://entitlements:4030
ENV ENTITY_HOST http://entity:4040
CMD /scripts/wait-for-service "${ENTITY_OBJECT_HOST}" \
    && /scripts/wait-for-service "${KAS_HOST}" \
    && /scripts/wait-for-service "${ATTRIBUTE_AUTHORITY_HOST}" \
    && /scripts/wait-for-service "${ENTITY_HOST}" \
    && /scripts/wait-for-service "${ENTITLEMENT_HOST}" \
    && python3 run_test.py --size 60 --step 20
