#!/usr/bin/env bash
#
# xtest CLI wrapper for the community Swift SDK (OpenTDFKit).
#
# Prefers OpenTDFKitCLI over the stub xtest/cli.swift.
# Stage-1 (KAS interop) is gated until OpenTDFKitCLI does client-credentials
# PublicKey fetch + RSA wrap encrypt and ephemeral rewrap decrypt.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <fmt>
#        ./cli.sh supports <feature>
#
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

BIN=""
for candidate in "$SCRIPT_DIR/OpenTDFKitCLI" "$SCRIPT_DIR/opentdfkit-cli"; do
  if [[ -x "$candidate" ]]; then
    BIN="$candidate"
    break
  fi
done

if [[ -z "$BIN" ]]; then
  echo "OpenTDFKitCLI binary not found in $SCRIPT_DIR (run make in sdk/swift)" >&2
  exit 1
fi

if [[ "${1:-}" == "supports" ]]; then
  # Delegate to OpenTDFKitCLI (Stage-1 KAS path is live).
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

# Dual allowlist env spellings
if [[ -z "${XT_WITH_KAS_ALLOW_LIST:-}" && -n "${XT_WITH_KAS_ALLOWLIST:-}" ]]; then
  export XT_WITH_KAS_ALLOW_LIST="$XT_WITH_KAS_ALLOWLIST"
fi

# Stage-1 KAS path: CLIENTID/CLIENTSECRET/PLATFORMURL/KASURL used by OpenTDFKitCLI.
exec "$BIN" "$@"
