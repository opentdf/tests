#!/usr/bin/env bash
# shellcheck disable=SC2206,SC1091

# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <nano>
#
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

# shellcheck source=../../test.env
source "$SCRIPT_DIR"/../../test.env

if [ "$1" == "supports" ]; then
  case "$2" in
    autoconfigure | ns_grants)
      exit 0
      ;;
    nano_ecdsa)
      java -jar "$SCRIPT_DIR"/cmdline.jar help encryptnano | grep ecdsa-binding
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
  -h
)
COMMAND="$1"
if [ "$4" == "nano" ]; then
  COMMAND="$1"nano
fi
args+=("$COMMAND")

if [ "$1" == "encrypt" ]; then
  args+=(--kas-url=$KASURL)

  if [ "$USE_ECDSA_BINDING" == "true" ]; then
    args+=(--ecdsa-binding "true")
  fi
fi

if [ -n "$5" ] && [ "$4" != "nano" ]; then
  args+=(--mime-type "$5")
fi

if [ -n "$6" ]; then
  args+=(--attr "$6")
fi

echo java -jar "$SCRIPT_DIR"/cmdline.jar "${args[@]}" -f "$2" ">" "$3"
java -jar "$SCRIPT_DIR"/cmdline.jar "${args[@]}" -f "$2" >"$3"
