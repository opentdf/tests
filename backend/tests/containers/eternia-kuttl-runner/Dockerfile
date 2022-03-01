FROM eternia-base

COPY tests /tests
COPY testdata /testdata

WORKDIR /build/packages/sdk-cli

RUN apt-get update && apt-get install -y \
    curl \
    jq    \
    --no-install-recommends

# ADD testdata .
ENV NODE_OPTIONS=--experimental-vm-modules
