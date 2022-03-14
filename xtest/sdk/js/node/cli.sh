#!/usr/bin/env bash

# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file>
#

env NODE_TLS_REJECT_UNAUTHORIZED=0 node --unhandled-rejections=strict \
  $(dirname "${BASH_SOURCE[0]}")/cli.js $1 -i $2 -o $3 "${@:4}"