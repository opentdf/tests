#!/usr/bin/env bash
#
# xtest CLI wrapper for the community Python SDK (otdf-python).
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <fmt>
#        ./cli.sh supports <feature>
#
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

# Prefer a venv/binary laid down by the Makefile; fall back to python -m.
if [[ -x "$SCRIPT_DIR/otdf-python" ]]; then
  PY_CMD=("$SCRIPT_DIR/otdf-python")
elif [[ -n "${OTDF_PYTHON_BIN:-}" ]]; then
  PY_CMD=("$OTDF_PYTHON_BIN")
elif [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  PY_CMD=("$SCRIPT_DIR/.venv/bin/python" -m otdf_python)
else
  PY_CMD=(python3 -m otdf_python)
fi

# ---------------------------------------------------------------------------
# supports <feature>
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "supports" ]]; then
  feature="${2:-}"
  if [[ -z "$feature" ]]; then
    echo "Usage: $0 supports <feature>" >&2
    exit 2
  fi
  # Prefer the SDK's own supports subcommand when present (otdf-python ≥ community xtest).
  if "${PY_CMD[@]}" supports --help &>/dev/null || "${PY_CMD[@]}" supports help &>/dev/null; then
    "${PY_CMD[@]}" supports "$feature"
    exit $?
  fi
  # Fallback static map for older packages without `supports`.
  case "$feature" in
    autoconfigure | connectrpc | hexless | kasallowlist)
      exit 0
      ;;
    assertions | assertion_verification | attribute_traversal | audit_logging | \
      better-messages-2024 | bulk_rewrap | dpop | dpop_nonce_challenge | ecwrap | \
      hexaflexible | key_management | mechanism-rsa-4096 | mechanism-ec-curves-384-521 | \
      mechanism-xwing | mechanism-secpmlkem | mechanism-mlkem | ns_grants | obligations)
      exit 1
      ;;
    *)
      echo "Unknown feature: $feature" >&2
      exit 2
      ;;
  esac
fi

# ---------------------------------------------------------------------------
# Locate xtest root + load test.env
# ---------------------------------------------------------------------------
XTEST_DIR="$SCRIPT_DIR"
while [[ "$XTEST_DIR" != "/" ]]; do
  if [[ -f "$XTEST_DIR/pyproject.toml" ]] && grep -q 'name = "xtest"' "$XTEST_DIR/pyproject.toml"; then
    break
  fi
  XTEST_DIR=$(dirname "$XTEST_DIR")
done

if [[ "$XTEST_DIR" == "/" ]]; then
  echo "xtest root (pyproject.toml with name = \"xtest\") not found." >&2
  exit 1
fi

if [[ -f "$XTEST_DIR/test.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  # shellcheck disable=SC1091
  source "$XTEST_DIR/test.env"
  set +a
else
  echo "test.env not found in xtest root: $XTEST_DIR" >&2
  exit 1
fi

cmd="${1:-}"
src="${2:-}"
dst="${3:-}"
fmt="${4:-}"

if [[ -z "$cmd" || -z "$src" || -z "$dst" ]]; then
  echo "Usage: $0 <encrypt|decrypt> <src> <dst> <fmt>" >&2
  exit 1
fi

# Parent-level flags (must appear before the subcommand for argparse).
# Prefer a temp credentials file over --client-secret on argv (ps(1) leakage).
# Newer otdf-python also reads CLIENTID/CLIENTSECRET from the environment.
parent_args=()
if [[ -n "${PLATFORMURL:-}" ]]; then
  parent_args+=(--platform-url "$PLATFORMURL")
fi
if [[ -n "${KASURL:-}" ]]; then
  parent_args+=(--kas-endpoint "$KASURL")
fi
if [[ -n "${KCFULLURL:-}" ]]; then
  parent_args+=(--oidc-endpoint "$KCFULLURL")
fi
# Local platform is typically HTTP.
if [[ "${PLATFORMURL:-}" == http://* ]]; then
  parent_args+=(--plaintext)
fi
parent_args+=(--insecure)

if [[ -n "${CLIENTID:-}" && -n "${CLIENTSECRET:-}" ]]; then
  _creds_file=$(mktemp)
  # shellcheck disable=SC2064
  trap 'rm -f "${_creds_file:-}"' EXIT
  printf '{"clientId":"%s","clientSecret":"%s"}\n' "$CLIENTID" "$CLIENTSECRET" >"$_creds_file"
  parent_args+=(--with-client-creds-file "$_creds_file")
fi

# Allowlist (both spellings accepted from harness)
allowlist="${XT_WITH_KAS_ALLOWLIST:-${XT_WITH_KAS_ALLOW_LIST:-}}"
if [[ -n "$allowlist" ]]; then
  parent_args+=(--kas-allowlist "$allowlist")
fi
if [[ "${XT_WITH_IGNORE_KAS_ALLOWLIST:-}" == "true" ]]; then
  parent_args+=(--ignore-kas-allowlist)
fi

# Base TDF only for Stage-1 (wire token may still be legacy "ztdf" from harness).
case "$fmt" in
  tdf | base-tdf | ztdf)
    container_type=tdf
    ;;
  tdf-ecwrap | ztdf-ecwrap)
    echo "ecwrap not supported by python community shim" >&2
    exit 1
    ;;
  *)
    echo "Unsupported container format for python: $fmt" >&2
    exit 2
    ;;
esac

if [[ "$cmd" == "encrypt" ]]; then
  enc_args=(encrypt "$src" --output "$dst" --container-type "$container_type")
  if [[ -n "${XT_WITH_MIME_TYPE:-}" ]]; then
    enc_args+=(--mime-type "$XT_WITH_MIME_TYPE")
  fi
  if [[ -n "${XT_WITH_ATTRIBUTES:-}" ]]; then
    enc_args+=(--attributes "$XT_WITH_ATTRIBUTES" --autoconfigure)
  fi
  echo "${PY_CMD[@]}" "${parent_args[@]}" "${enc_args[@]}"
  "${PY_CMD[@]}" "${parent_args[@]}" "${enc_args[@]}"
elif [[ "$cmd" == "decrypt" ]]; then
  dec_args=(decrypt "$src" --output "$dst")
  echo "${PY_CMD[@]}" "${parent_args[@]}" "${dec_args[@]}"
  "${PY_CMD[@]}" "${parent_args[@]}" "${dec_args[@]}"
else
  echo "Incorrect argument provided: $cmd" >&2
  exit 1
fi
