#!/usr/bin/env bash
# shellcheck disable=SC2206,SC1091

# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <nano>
#
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# shellcheck source=../../test.env
source "$SCRIPT_DIR"/../../test.env

python3 "$(dirname "${BASH_SOURCE[0]}")"/cli.py "$1" "$2" "$3" "$4" "${@:5}"
