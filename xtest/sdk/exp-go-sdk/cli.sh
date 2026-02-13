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

cmd="$SCRIPT_DIR/exp-go-sdk"
if [ ! -f "$cmd" ]; then
  echo "exp-go-sdk binary not found at $cmd"
  exit 1
fi

if [ "$1" == "supports" ]; then
  "$cmd" supports "$2"
  exit $?
fi

XTEST_DIR="$SCRIPT_DIR"
while [ ! -f "$XTEST_DIR/test.env" ] && [ "$(basename "$XTEST_DIR")" != "xtest" ]; do
  XTEST_DIR=$(dirname "$XTEST_DIR")
done

if [ -f "$XTEST_DIR/test.env" ]; then
  # shellcheck disable=SC1091
  source "$XTEST_DIR/test.env"
else
  echo "test.env not found, stopping at xtest directory."
  exit 1
fi

if [ "$4" != "ztdf" ]; then
  echo "Unsupported container format: $4"
  exit 2
fi

args=(
  --output "$3"
  --platform-endpoint "$PLATFORMURL"
  --client-id "$CLIENTID"
  --client-secret "$CLIENTSECRET"
)

if [ "$1" == "encrypt" ]; then
  if [ -n "$XT_WITH_MIME_TYPE" ]; then
    args+=(--mime-type "$XT_WITH_MIME_TYPE")
  fi

  if [ -n "$XT_WITH_ATTRIBUTES" ]; then
    args+=(--attributes "$XT_WITH_ATTRIBUTES")
  fi

  if [ -n "$XT_WITH_ASSERTIONS" ]; then
    args+=(--assertions "$XT_WITH_ASSERTIONS")
  fi

  if [ "$XT_WITH_ECWRAP" == "true" ]; then
    args+=(--ecwrap)
  fi

  echo "$cmd" encrypt "${args[@]}" "$2"
  "$cmd" encrypt "${args[@]}" "$2"
elif [ "$1" == "decrypt" ]; then
  if [ -n "$XT_WITH_ASSERTION_VERIFICATION_KEYS" ]; then
    args+=(--assertion-verification-keys "$XT_WITH_ASSERTION_VERIFICATION_KEYS")
  fi
  if [ "$XT_WITH_VERIFY_ASSERTIONS" == 'false' ]; then
    args+=(--no-verify-assertions)
  fi
  if [ -n "$XT_WITH_KAS_ALLOWLIST" ]; then
    args+=(--kas-allowlist "$XT_WITH_KAS_ALLOWLIST")
  fi
  if [ "$XT_WITH_IGNORE_KAS_ALLOWLIST" == "true" ]; then
    args+=(--ignore-kas-allowlist)
  fi

  echo "$cmd" decrypt "${args[@]}" "$2"
  "$cmd" decrypt "${args[@]}" "$2"
else
  echo "Incorrect argument provided"
  exit 1
fi
