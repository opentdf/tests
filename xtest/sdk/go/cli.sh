#!/usr/bin/env bash
# shellcheck disable=SC2206,SC1091

# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <fmt> <mimeType> <attrs> <assertions> <assertionverificationkeys>
#
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

# shellcheck source=../../test.env
source "$SCRIPT_DIR"/../../test.env

cmd=("$SCRIPT_DIR"/otdfctl)
if [ ! -f "$SCRIPT_DIR"/otdfctl ]; then
  cmd=(go run github.com/opentdf/otdfctl@${OTDFCTL_REF-latest})
fi

if [ "$1" == "supports" ]; then
  case "$2" in
    autoconfigure | nano_ecdsa | ns_grants)
      exit 0
      ;;
    assertions)
      "${cmd[@]}" help encrypt | grep with-assertions
      exit $?
      ;;
    assertion_verification)
      "${cmd[@]}" help decrypt | grep with-assertion-verification-keys
      exit $?
      ;;
    ecwrap)
      "${cmd[@]}" help encrypt | grep wrapping-key
      exit $?
      ;;
    hexless)
      set -o pipefail
      "${cmd[@]}" --version --json | jq -re .schema_version | awk -F. '{ if ($1 > 4 || ($1 == 4 && $2 > 2) || ($1 == 4 && $2 == 3 && $3 >= 0)) exit 0; else exit 1; }'
      exit $?
      ;;
    *)
      echo "Unknown feature: $2"
      exit 2
      ;;
  esac
fi

args=(
  -o "$3"
  --host "$PLATFORMURL"
  --tls-no-verify
  --log-level debug
  --with-client-creds '{"clientId":"'$CLIENTID'","clientSecret":"'$CLIENTSECRET'"}'
)
if [ "$4" == "nano" ]; then
  args+=(--tdf-type "$4")
fi

if [ "$1" == "encrypt" ]; then
  if [ -n "$5" ]; then
    args+=(--mime-type "$5")
  fi

  if [ -n "$6" ]; then
    args+=(--attr "$6")
  fi

  if [ -n "$7" ]; then
    args+=(--with-assertions "$7")
  fi
  if [ "$ECWRAP" == 'true' ]; then
    args+=(--wrapping-key-algorithm "ec:secp256r1")
  fi
  if [ "$USE_ECDSA_BINDING" == "true" ]; then
    args+=(--ecdsa-binding)
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
  if [ -n "$8" ]; then
    args+=(--with-assertion-verification-keys "$8")
  fi
  if [ "$ECWRAP" == 'true' ]; then
    args+=(--session-key-algorithm "ec:secp256r1")
  fi
  if [ "$VERIFY_ASSERTIONS" == 'false' ]; then
    args+=(--no-verify-assertions)
  fi
  echo "${cmd[@]}" decrypt "${args[@]}" "$2"
  "${cmd[@]}" decrypt "${args[@]}" "$2"
else
  echo "Incorrect argument provided"
  exit 1
fi
