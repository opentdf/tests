#!/usr/bin/env bash
# shellcheck disable=SC2206,SC1091

# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <nano>
#
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

# shellcheck source=../../../test.env
source "$SCRIPT_DIR"/../../../test.env

if [ "$1" == "supports" ]; then
  case "$2" in
    autoconfigure)
      npx @opentdf/cli help | grep autoconfigure
      exit $?
      ;;
    *)
      echo "Unknown feature: $2"
      exit 2
      ;;
  esac
fi

args=(
  --output "$3"
  --kasEndpoint "$KASURL"
  --ignoreAllowList
  --oidcEndpoint "$KCFULLURL"
  --auth opentdf:secret
)
# default for js cli is nano
if [ "$4" == "ztdf" ]; then
  args+=(--containerType tdf3)
fi

if [ -n "$6" ]; then
  args+=(--attributes "$6")
fi

if [ "$1" == "encrypt" ]; then
  if npx @opentdf/cli help | grep autoconfigure; then
    args+=(--policyEndpoint "$PLATFORMURL" --autoconfigure true)
  fi

  npx @opentdf/cli encrypt "$2" "${args[@]}"
elif [ "$1" == "decrypt" ]; then
  npx @opentdf/cli decrypt "$2" "${args[@]}"
else
  echo "Incorrect argument provided"
  exit 1
fi
