#!/usr/bin/env bash

# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file>
#

env NODE_TLS_REJECT_UNAUTHORIZED=0 npx --unhandled-rejections=strict \
  @opentdf/cli --clientId=tdf-client --clientSecret=123-456 \
  --oidcEndpoint="http://localhost:65432/auth/realms/tdf" \
  --kasEndpoint="http://localhost:65432/api/kas" \
  "$1" -i "$2" -o "$3" "${@:4}"
