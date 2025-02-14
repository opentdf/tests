#!/usr/bin/env bash
# shellcheck disable=SC2206,SC1091

# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <fmt> <mimeType> <attrs> <assertions> <assertionverificationkeys>
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
    assertion_verification)
      npx $CTL help | grep assertionVerificationKeys
      exit $?
      ;;
    autoconfigure | ns_grants)
      npx $CTL help | grep autoconfigure
      exit $?
      ;;
    ecwrap)
      npx $CTL help | grep encapsulation-algorithm
      exit $?
      ;;
    hexless)
      set -o pipefail
      npx $CTL --version | jq -re .tdfSpecVersion | awk -F. '{ if ($1 > 4 || ($1 == 4 && $2 > 2) || ($1 == 4 && $2 == 3 && $3 >= 0)) exit 0; else exit 1; }'
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

if [ -n "$8" ]; then
  args+=(--assertionVerificationKeys "$8")
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
  if [ "$ECWRAP" == 'true' ]; then
    args+=(--encapKeyType "ec:secp256r1")
  fi

  npx $CTL encrypt "$2" "${args[@]}"
elif [ "$1" == "decrypt" ]; then
  if [ "$VERIFY_ASSERTIONS" == 'false' ]; then
    args+=(--noVerifyAssertions)
  fi
  if [ "$ECWRAP" == 'true' ]; then
    args+=(--rewrapKeyType "ec:secp256r1")
  fi
  npx $CTL decrypt "$2" "${args[@]}"
else
  echo "Incorrect argument provided"
  exit 1
fi
