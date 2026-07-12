#!/usr/bin/env bash
#
# xtest CLI wrapper for the community Rust SDK (opentdf-rs).
#
# Stage-1 (KAS interop) is gated until xtest_cli speaks CLIENTID/PLATFORMURL
# and emits RSA-wrapped key access objects. Until then this shim either:
#   - reports honest supports (mostly unsupported for official feature_type)
#   - runs offline self-tests only when XT_ALLOW_OFFLINE=1
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <fmt>
#        ./cli.sh supports <feature>
#
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

BIN=""
for candidate in "$SCRIPT_DIR/xtest_cli" "$SCRIPT_DIR/opentdf-xtest-cli"; do
  if [[ -x "$candidate" ]]; then
    BIN="$candidate"
    break
  fi
done

if [[ -z "$BIN" ]]; then
  echo "rust xtest CLI binary not found in $SCRIPT_DIR (run make in sdk/rust)" >&2
  exit 1
fi

if [[ "${1:-}" == "supports" ]]; then
  # Delegate to binary (honest Stage-1 feature map).
  exec "$BIN" supports "${2:-}"
fi

XTEST_DIR="$SCRIPT_DIR"
while [[ "$XTEST_DIR" != "/" ]]; do
  if [[ -f "$XTEST_DIR/pyproject.toml" ]] && grep -q 'name = "xtest"' "$XTEST_DIR/pyproject.toml"; then
    break
  fi
  XTEST_DIR=$(dirname "$XTEST_DIR")
done
if [[ -f "$XTEST_DIR/test.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$XTEST_DIR/test.env"
  set +a
fi

# Map official env into rust vars when present.
export TDF_KAS_URL="${TDF_KAS_URL:-${KASURL:-http://localhost:8080/kas}}"
export KASURL="${KASURL:-$TDF_KAS_URL}"

# Stage-1 KAS path is live (RSA wrap + client_credentials rewrap).
# Offline-only mode still available via TDF_SYMMETRIC_KEY_PATH / TDF_KAS_PUBLIC_KEY_PATH.
exec "$BIN" "$@"
