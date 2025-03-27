#!/usr/bin/env bash
# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <fmt> <mimeType> <attrs> <assertions> <assertionverificationkeys>
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
      java -jar "$SCRIPT_DIR"/cmdline.jar help encryptnano | grep ecdsa-binding
      exit $?
      ;;
    assertions)
      java -jar "$SCRIPT_DIR"/cmdline.jar help encrypt | grep with-assertions
      exit $?
      ;;
    assertion_verification)
      java -jar "$SCRIPT_DIR"/cmdline.jar help decrypt | grep with-assertion-verification-keys
      exit $?
      ;;

    ecwrap)
      java -jar "$SCRIPT_DIR"/cmdline.jar help encrypt | grep encap-key
      exit $?
      ;;

    hexless)
      set -o pipefail
      java -jar "$SCRIPT_DIR"/cmdline.jar --version | jq -re .tdfSpecVersion | awk -F. '{ if ($1 > 4 || ($1 == 4 && $2 > 2) || ($1 == 4 && $2 == 3 && $3 >= 0)) exit 0; else exit 1; }'
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
  "--platform-endpoint=$PLATFORMENDPOINT"
  "--plaintext"
)
COMMAND="$1"
if [[ $4 == nano* ]]; then
  COMMAND="$1"nano
fi
args+=("$COMMAND")

if [ "$1" == "encrypt" ]; then
  args+=("--kas-url=$KASURL")

  if [ "$USE_ECDSA_BINDING" == "true" ]; then
    args+=(--ecdsa-binding)
  fi

  if [ "$ECWRAP" == 'true' ]; then
    args+=(--encap-key-type="ec:secp256r1")
  fi
else
  if [ "$ECWRAP" == 'true' ]; then
    args+=(--rewrap-key-type="ec:secp256r1")
  fi
fi

if [ -n "$5" ] && [ "$4" != "nano" ]; then
  args+=(--mime-type "$5")
fi

if [ -n "$6" ]; then
  args+=(--attr "$6")
fi

if [ -n "$7" ]; then
  args+=(--with-assertions "$7")
fi

if [ -n "$8" ]; then
  args+=(--with-assertion-verification-keys "$8")
fi

if [ "$VERIFY_ASSERTIONS" == 'false' ]; then
  args+=(--with-assertion-verification-disabled)
fi

echo java -jar "$SCRIPT_DIR"/cmdline.jar "${args[@]}" --file="$2" ">" "$3"
java -jar "$SCRIPT_DIR"/cmdline.jar "${args[@]}" --file="$2" >"$3"
