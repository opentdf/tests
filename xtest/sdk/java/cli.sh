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
#  XT_WITH_TARGET_MODE [string] - Target spec mode for the encrypted file
#
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

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

if [ "$1" == "supports" ]; then
  case "$2" in
    autoconfigure | ns_grants)
      exit 0
      ;;
    nano_ecdsa)
      if java -jar "$SCRIPT_DIR"/cmdline.jar help encryptnano | grep ecdsa-binding; then
        # Java version 0.7.7 fixwa a bug in the ECDSA parsing for nano
        java -jar "$SCRIPT_DIR"/cmdline.jar --version | jq -re .version | awk -F. '{ if ($1 > 0 || ($1 == 0 && $2 > 7) || ($1 == 0 && $2 == 7 && $3 >= 7)) exit 0; else exit 1; }'
        exit $?
      else
        echo "ecdsa-binding not supported"
        exit 1
      fi
      ;;
    assertions)
      java -jar "$SCRIPT_DIR"/cmdline.jar help encrypt | grep with-assertions
      exit $?
      ;;
    assertion_verification)
      java -jar "$SCRIPT_DIR"/cmdline.jar help decrypt | grep with-assertion-verification-keys
      exit $?
      ;;
    kasallowlist)
      java -jar "$SCRIPT_DIR"/cmdline.jar help decrypt | grep kas-allowlist
      exit $?
      ;;
    ecwrap)
      if java -jar "$SCRIPT_DIR"/cmdline.jar help encrypt | grep encap-key; then
        # versions 0.7.6 and earlier used an older value for EC HKDF salt; check for 0.7.7 or later
        java -jar "$SCRIPT_DIR"/cmdline.jar --version | jq -re .version | awk -F. '{ if ($1 > 0 || ($1 == 0 && $2 > 7) || ($1 == 0 && $2 == 7 && $3 >= 7)) exit 0; else exit 1; }'
        exit $?
      else
        echo "ecwrap not supported"
        exit 1
      fi
      ;;

    hexless)
      set -o pipefail
      java -jar "$SCRIPT_DIR"/cmdline.jar --version | jq -re .tdfSpecVersion | awk -F. '{ if ($1 > 4 || ($1 == 4 && $2 > 2) || ($1 == 4 && $2 == 3 && $3 >= 0)) exit 0; else exit 1; }'
      exit $?
      ;;

    hexaflexible)
      java -jar "$SCRIPT_DIR"/cmdline.jar help encrypt | grep with-target-mode
      exit $?
      ;;

    *)
      echo "Unknown feature: $2"
      exit 2
      ;;
  esac
fi

args=(
  "--client-id=$CLIENTID"
  "--client-secret=$CLIENTSECRET"
  "--plaintext"
)

# when we added support for KAS allowlist, we changed the platform endpoint format to require scheme
if java -jar "$SCRIPT_DIR"/cmdline.jar help decrypt | grep kas-allowlist; then
  args+=("--platform-endpoint=$PLATFORMURL")
else
  args+=("--platform-endpoint=$PLATFORMENDPOINT")
fi

COMMAND="$1"
if [[ $4 == nano* ]]; then
  COMMAND="$1"nano
fi
args+=("$COMMAND")

if [ "$1" == "encrypt" ]; then
  args+=("--kas-url=$KASURL")

  if [ "$XT_WITH_ECDSA_BINDING" == "true" ]; then
    args+=(--ecdsa-binding)
  fi

  if [ "$XT_WITH_ECWRAP" == 'true' ]; then
    args+=(--encap-key-type="ec:secp256r1")
  fi
else
  if [ "$XT_WITH_ECWRAP" == 'true' ]; then
    args+=(--rewrap-key-type="ec:secp256r1")
  fi
fi

if [ "$1" == "decrypt" ]; then
  if [ -n "$XT_WITH_KAS_ALLOW_LIST" ]; then
    args+=(--kas-allowlist "$XT_WITH_KAS_ALLOW_LIST")
  fi

  if [ "$XT_WITH_IGNORE_KAS_ALLOWLIST" == "true" ]; then
    args+=(--ignore-kas-allowlist)
  fi
fi

if [ -n "$XT_WITH_MIME_TYPE" ] && [ "$4" != "nano" ]; then
  args+=(--mime-type "$XT_WITH_MIME_TYPE")
fi

if [ -n "$XT_WITH_ATTRIBUTES" ]; then
  args+=(--attr "$XT_WITH_ATTRIBUTES")
fi

if [ -n "$XT_WITH_ASSERTIONS" ]; then
  args+=(--with-assertions "$XT_WITH_ASSERTIONS")
fi

if [ -n "$XT_WITH_ASSERTION_VERIFICATION_KEYS" ]; then
  args+=(--with-assertion-verification-keys "$XT_WITH_ASSERTION_VERIFICATION_KEYS")
fi



if [ "$XT_WITH_VERIFY_ASSERTIONS" == 'false' ]; then
  args+=(--with-assertion-verification-disabled)
fi

if [ -n "$XT_WITH_TARGET_MODE" ]; then
  args+=(--with-target-mode "$XT_WITH_TARGET_MODE")
fi

echo java -jar "$SCRIPT_DIR"/cmdline.jar "${args[@]}" --file="$2" ">" "$3"
java -jar "$SCRIPT_DIR"/cmdline.jar "${args[@]}" --file="$2" >"$3"
