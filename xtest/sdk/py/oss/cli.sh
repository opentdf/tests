#!/usr/bin/env bash
# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <uid> <tier> <encrypt | decrypt> <src-file> <dst-file>

PY_CLI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd)"
PROJECT_ROOT="$(cd "${PY_CLI_DIR}/../../../../" >/dev/null && pwd)"
export PATH="$PATH:$PROJECT_ROOT/scripts"

monolog DEBUG "cwd=[$(pwd)] PY_CLI_DIR=$PY_CLI_DIR PROJECT_ROOT=$PROJECT_ROOT $1 $2 $3 $4 $5 $6 $7"

function install_and_run() {
  monolog DEBUG "python3 --version == [$(python3 --version 2>&1)]"
  monolog DEBUG "pip3 --version == [$(python3 --version 2>&1)]"

  pip3 install -r "$1"
  shift

  monolog TRACE "Running $*"
  python3 "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" "$9"
}

export -f install_and_run

OWNER=$1
shift

STAGE=$1
shift

ACTION=$1
shift

SOURCE=$1
shift

TARGET=$1
shift

# TODO(PLAT-532) Support manifest access
if [[ $ACTION == "manifest" ]]; then
  VIRTRU_SDK_EMAIL=$OWNER ${PROJECT_ROOT}/xtest/sdk/js/headless/cli.sh $STAGE manifest "$SOURCE" "$TARGET" "$1" "$2" "$3"
  exit
fi

if [[ $TDF3_CERT_AUTHORITY && ! $CERT_CLIENT_BASE ]]; then
  cn=$(sed 's/^CN=\([^,]*\).*/\1/' <<<$OWNER)
  if [ -f ${PROJECT_ROOT}/xtest/${cn}.crt ]; then
    export CERT_CLIENT_BASE=${PROJECT_ROOT}/xtest/${cn}
  else
    export CERT_CLIENT_BASE=${PROJECT_ROOT}/certs/${cn}
  fi
  monolog DEBUG "CERT_CLIENT_BASE=${CERT_CLIENT_BASE}"
fi

venvelop --clean py_cli install_and_run "${PY_CLI_DIR}/requirements.txt" "${PY_CLI_DIR}/${ACTION}.py" \
  "$STAGE" "$SOURCE" "$TARGET" "$OWNER" "${@}"
