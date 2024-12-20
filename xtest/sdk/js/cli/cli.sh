#!/usr/bin/env bash
# shellcheck disable=SC2206,SC1091

# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <nano>
#
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
XTEST_DIR=$(cd -- "$SCRIPT_DIR"/../../../ &>/dev/null && pwd)

# shellcheck source=../../../test.env
source "$XTEST_DIR"/test.env

CTL=@opentdf/ctl
if grep opentdf/cli "$XTEST_DIR"/package.json; then
  CTL=@opentdf/cli
fi

if [ "$1" == "supports" ]; then
  case "$2" in
    assertions)
      npx $CTL help | grep assertions
      exit $?
      ;;
    autoconfigure | ns_grants)
      npx $CTL help | grep autoconfigure
      exit $?
      ;;
    nano_ecdsa)
      npx $CTL help | grep policyBinding
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

if [ -n "$7" ]; then
  args+=(--assertions "$7")
fi

if [ "$1" == "encrypt" ]; then
  if npx $CTL help | grep autoconfigure; then
    args+=(--policyEndpoint "$PLATFORMURL" --autoconfigure true)
  fi

  if [ -n "$USE_ECDSA_BINDING" ]; then
    if [ "$USE_ECDSA_BINDING" == "true" ]; then
      args+=(--policyBinding ecdsa)
    fi
  fi

  npx $CTL encrypt "$2" "${args[@]}"
elif [ "$1" == "decrypt" ]; then
  printf 'performing decryption with [%s] [%s] [%s]\n' $CTL "$2" "${args[@]}"
  npx $CTL decrypt "$2" "${args[@]}"
else
  echo "Incorrect argument provided"
  exit 1
fi
