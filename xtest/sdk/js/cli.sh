#!/usr/bin/env bash
# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <fmt> <mimeType> <attrs> <assertions> <assertionverificationkeys>
#

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)


CTL=@opentdf/ctl
if grep opentdf/cli "$SCRIPT_DIR/package.json"; then
  CTL=@opentdf/cli
fi

if [ "$1" == "supports" ]; then
  if ! cd "$SCRIPT_DIR"; then
    echo "failed: [cd $SCRIPT_DIR]"
    exit 1
  fi
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
      npx $CTL help | grep encapKeyType
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

XTEST_DIR=$SCRIPT_DIR
while [ "$XTEST_DIR" != "/" ]; do
  if [ -d "$XTEST_DIR/xtest" ]; then
    XTEST_DIR="$XTEST_DIR/xtest"
    break
  fi
  XTEST_DIR=$(dirname "$XTEST_DIR")
done

# shellcheck source=../../test.env
source "$XTEST_DIR"/test.env

src_file=$(realpath "$2")
dst_file=$(realpath "$3")

args=(
  --output "$dst_file"
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

  npx $CTL encrypt "$src_file" "${args[@]}"
elif [ "$1" == "decrypt" ]; then
  if [ "$VERIFY_ASSERTIONS" == 'false' ]; then
    args+=(--noVerifyAssertions)
  fi
  if [ "$ECWRAP" == 'true' ]; then
    args+=(--rewrapKeyType "ec:secp256r1")
  fi
  npx $CTL decrypt "$src_file" "${args[@]}"
else
  echo "Incorrect argument provided"
  exit 1
fi
