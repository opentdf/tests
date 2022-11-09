#!/usr/bin/env bash

# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file>
#

python3 "$(dirname "${BASH_SOURCE[0]}")"/cli.py "$1" "$2" "$3" "${@:4}"
