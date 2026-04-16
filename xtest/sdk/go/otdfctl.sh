#!/usr/bin/env bash
# shellcheck disable=SC2206,SC1091

# Wrapper for go otdfctl to quickly switch between local and released versions.
#
# Usage: ./otdfctl.sh [otdfctl options]
#
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null  && pwd)

XTEST_DIR="$SCRIPT_DIR"
while [ ! -f "$XTEST_DIR/test.env" ] && [ "$(basename "$XTEST_DIR")" != "xtest" ]; do
  XTEST_DIR=$(dirname "$XTEST_DIR")
done

# shellcheck source=../../test.env
source "$XTEST_DIR/test.env"

cmd=("$SCRIPT_DIR"/otdfctl)
if [ ! -f "$SCRIPT_DIR"/otdfctl ]; then
  if [ -f "$SCRIPT_DIR/.version" ]; then
    VERSION_SPEC=$(tr -d '[:space:]' <"$SCRIPT_DIR/.version")
    if [[ "$VERSION_SPEC" == *@* ]]; then
      # New format: module-path@version
      cmd=(go run "$VERSION_SPEC")
    else
      # Legacy format: bare version tag, default to standalone module
      cmd=(go run "github.com/opentdf/otdfctl@${VERSION_SPEC}")
    fi
  else
    cmd=(go run "github.com/opentdf/otdfctl@latest")
  fi
fi

cmd+=(--json)
cmd+=(--host="$PLATFORMURL" --tls-no-verify --log-level=debug)
cmd+=(--with-client-creds='{"clientId":"'$CLIENTID'","clientSecret":"'$CLIENTSECRET'"}')

echo >&2 "${cmd[@]}" "$@"
"${cmd[@]}" "$@"
