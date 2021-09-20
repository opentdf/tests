#!/usr/bin/env bash
# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <owner> <tier> <encrypt | decrypt> <src-file> <dst-file>
#
env NODE_TLS_REJECT_UNAUTHORIZED=0 node --unhandled-rejections=strict \
  $(dirname "${BASH_SOURCE[0]}")/cli.js \
  -u $1 -s $2 $3 -i $4 -o $5 "${@:6}"
