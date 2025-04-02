#!/usr/bin/env bash
#
# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <fmt>
#
# Extended Utilities:
#
# ./cli.sh supports <feature>
#   Check if the SDK supports a specific feature.
#
# Extended Configuration:
#  XT_WITH_ECDSA_BINDING [boolean] - Use ECDSA binding for encryption
#  XT_WITH_ECWRAP [boolean] - Use EC wrap for encryption/decryption
#  XT_WITH_VERIFY_ASSERTIONS [boolean] - Verify assertions during decryption
#  XT_WITH_ASSERTIONS [string] - Path to assertions file, or JSON encoded as string
#  XT_WITH_ASSERTION_VERIFICATION_KEYS [string] - Path to assertion verification private key file
#  XT_WITH_ATTRIBUTES [string] - Attributes to be used for encryption
#  XT_WITH_MIME_TYPE [string] - MIME type for the encrypted file
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
      if npx $CTL help | grep encapKeyType; then
        # Claims to support ecwrap, but maybe with old salt? Look up version
        npx $CTL --version | jq -re '.["@opentdf/sdk"]' | awk -F. '{ if ($1 > 2) exit 0; else exit 1; }'
        exit $?
      else
        echo "ecwrap not supported"
        exit 1
      fi
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

# shellcheck disable=SC1091
source "$XTEST_DIR"/test.env

src_file=$(realpath "$2")
dst_file=$(realpath "$(dirname "$3")")/$(basename "$3")

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

if [ -n "$XT_WITH_ATTRIBUTES" ]; then
  attributes="$XT_WITH_ATTRIBUTES"
  if [ -f "$attributes" ]; then
    attributes=$(realpath "$attributes")
    echo "Attributes are a file: $attributes"
    args+=(--attributes "$attributes")
  else
    # Attributes are a comma separated list
    echo "Attributes are: $attributes"
    args+=(--attributes "$attributes")
  fi
fi

if [ -n "$XT_WITH_ASSERTIONS" ]; then
  assertions="$XT_WITH_ASSERTIONS"
  if [ -f "$assertions" ]; then
    assertions=$(realpath "$assertions")
    echo "Assertions are a file: $assertions"
    args+=(--assertions "$assertions")
  elif [ "$(echo "$assertions" | jq -e . >/dev/null 2>&1 && echo valid || echo invalid)" == "valid" ]; then
    # Assertions are plain json
    echo "Assertions are plain json: $assertions"
    args+=(--assertions "$assertions")
  else
    echo "Invalid or missing assertion file: $assertions"
    exit 1
  fi
fi

if [ -n "$XT_WITH_ASSERTION_VERIFICATION_KEYS" ]; then
  verification_keys="$XT_WITH_ASSERTION_VERIFICATION_KEYS"
  if [ -f "$verification_keys" ]; then
    verification_keys=$(realpath "$verification_keys")
    echo "Verification keys are a file: $verification_keys"
    args+=(--assertionVerificationKeys "$verification_keys")
  else
    echo "Invalid or missing verification keys file: $verification_keys"
    exit 1
  fi
fi

if ! cd "$SCRIPT_DIR"; then
  echo "failed: [cd $SCRIPT_DIR]"
  exit 1
fi

if [ "$1" == "encrypt" ]; then
  if npx $CTL help | grep autoconfigure; then
    args+=(--policyEndpoint "$PLATFORMURL" --autoconfigure true)
  fi
  if [ -n "$XT_WITH_ECDSA_BINDING" ]; then
    if [ "$XT_WITH_ECDSA_BINDING" == "true" ]; then
      args+=(--policyBinding ecdsa)
    fi
  fi
  if [ "$XT_WITH_ECWRAP" == 'true' ]; then
    args+=(--encapKeyType "ec:secp256r1")
  fi

  echo npx $CTL encrypt "$src_file" "${args[@]}"
  npx $CTL encrypt "$src_file" "${args[@]}"
elif [ "$1" == "decrypt" ]; then
  if [ "$XT_WITH_VERIFY_ASSERTIONS" == 'false' ]; then
    args+=(--noVerifyAssertions)
  fi
  if [ "$XT_WITH_ECWRAP" == 'true' ]; then
    args+=(--rewrapKeyType "ec:secp256r1")
  fi
  echo npx $CTL decrypt "$src_file" "${args[@]}"
  npx $CTL decrypt "$src_file" "${args[@]}"
else
  echo "Incorrect argument provided"
  exit 1
fi
