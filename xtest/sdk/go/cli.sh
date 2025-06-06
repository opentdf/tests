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

cmd=("$SCRIPT_DIR"/otdfctl)
if [ ! -f "$SCRIPT_DIR"/otdfctl ]; then
  cmd=(go run "github.com/opentdf/otdfctl@latest")
fi

if [ "$1" == "supports" ]; then
  case "$2" in
    autoconfigure | nano_ecdsa | ns_grants)
      exit 0
      ;;
    assertions | assertion_verification)
      "${cmd[@]}" help decrypt | grep with-assertion-verification-keys
      exit $?
      ;;
    kasallowlist)
      "${cmd[@]}" help decrypt | grep kas-allowlist
      exit $?
      ;;
    ecwrap)
      if "${cmd[@]}" help encrypt | grep wrapping-key; then
        # while the otdfctl app may support ecwrap, but sdk versions 0.3.28 and earlier uses the old salt
        set -o pipefail
        "${cmd[@]}" --version --json | jq -re .sdk_version | awk -F. '{ if ($1 > 0 || ($1 == 0 && $2 > 3) || ($1 == 0 && $2 == 3 && $3 >= 29)) exit 0; else exit 1; }'
        exit $?
      else
        echo "ecwrap not supported"
        exit 1
      fi
      ;;
    hexless)
      set -o pipefail
      # Schema version 4.3.0 introduced hexless
      "${cmd[@]}" --version --json | jq -re .schema_version | awk -F. '{ if ($1 > 4 || ($1 == 4 && $2 >= 2)) exit 0; else exit 1; }'
      exit $?
      ;;
    hexaflexible)
      "${cmd[@]}" help encrypt | grep target-mode
      exit $?
      ;;
    connectrpc)
      set -o pipefail
      # SDK version 0.4.5 introduces connectrpc client side
      "${cmd[@]}" --version --json | jq -re .sdk_version | awk -F. '{ if ($1 > 0 || ($1 == 0 && $2 > 4) || ($1 == 0 && $2 == 4 && $3 >= 5)) exit 0; else exit 1; }'
      exit $?
      ;;
    better-messages-2024)
      # In November 2024, we added more. detailed error messages
      # These appeared in go sdk 0.3.28
      set -o pipefail
      "${cmd[@]}" --version --json | jq -re .sdk_version | awk -F. '{ if ($1 > 0 || ($1 == 0 && $2 > 3) || ($1 == 0 && $2 == 3 && $3 >= 18)) exit 0; else exit 1; }'
      exit $?
      ;;
    public-client-id)
      # this was removed in 0.21.0
      set -o pipefail
      "${cmd[@]}" --version --json | jq -re .version | awk -F. '{ if ($1 == 0 && $2 < 21) exit 0; else exit 1; }'
      exit $?
      ;;
    *)
      echo "Unknown feature: $2"
      exit 2
      ;;
  esac
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

args=(
  -o "$3"
  --host "$PLATFORMURL"
  --tls-no-verify
  --log-level debug
  --with-client-creds '{"clientId":"'"$CLIENTID"'","clientSecret":"'"$CLIENTSECRET"'"}'
)
if [ "$4" == "nano" ]; then
  args+=(--tdf-type "$4")
fi

if [ "$1" == "encrypt" ]; then
  if [ -n "$XT_WITH_MIME_TYPE" ]; then
    args+=(--mime-type "$XT_WITH_MIME_TYPE")
  fi

  if [ -n "$XT_WITH_ATTRIBUTES" ]; then
    args+=(--attr "$XT_WITH_ATTRIBUTES")
  fi

  if [ -n "$XT_WITH_ASSERTIONS" ]; then
    args+=(--with-assertions "$XT_WITH_ASSERTIONS")
  fi
  if [ "$XT_WITH_ECWRAP" == 'true' ]; then
    args+=(--wrapping-key-algorithm "ec:secp256r1")
  fi
  if [ "$XT_WITH_ECDSA_BINDING" == "true" ]; then
    args+=(--ecdsa-binding)
  fi
  if [ -n "$XT_WITH_TARGET_MODE" ]; then
    args+=(--target-mode "$XT_WITH_TARGET_MODE")
  fi
  echo "${cmd[@]}" encrypt "${args[@]}" "$2"
  if ! "${cmd[@]}" encrypt "${args[@]}" "$2"; then
    exit 1
  fi
  if [ -f "${3}.tdf" ]; then
    # go helpfully adds a tdf extension to all files
    mv "${3}.tdf" "${3}"
  fi
elif [ "$1" == "decrypt" ]; then
  if [ -n "$XT_WITH_ASSERTION_VERIFICATION_KEYS" ]; then
    args+=(--with-assertion-verification-keys "$XT_WITH_ASSERTION_VERIFICATION_KEYS")
  fi
  if [ "$XT_WITH_ECWRAP" == 'true' ]; then
    args+=(--session-key-algorithm "ec:secp256r1")
  fi
  if [ "$XT_WITH_VERIFY_ASSERTIONS" == 'false' ]; then
    args+=(--no-verify-assertions)
  fi
  echo "${cmd[@]}" decrypt "${args[@]}" "$2"
  "${cmd[@]}" decrypt "${args[@]}" "$2"
else
  echo "Incorrect argument provided"
  exit 1
fi
