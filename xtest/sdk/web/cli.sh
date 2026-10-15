#!/usr/bin/env bash
#
# Common shell wrapper used to interface to SDK implementation.
#
# The `web` flavour runs @opentdf/sdk (web-sdk's library) inside a headless
# browser driven by Playwright, rather than through the Node CLI the `js`
# flavour uses. Same library, different runtime: this is what catches
# browser-only behaviour, and what tells a Node bug (e.g. DSPX-5160, where
# fs.openAsBlob truncates Blob sizes to 32 bits) apart from an SDK bug.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <fmt>
#
# Extended Utilities:
#
# ./cli.sh supports <feature>
#   Check if the SDK supports a specific feature. Answered from
#   features.json, which build.mjs writes from the bundled library at install
#   time, so no browser is launched.
#
# Extended Configuration:
#  XT_WITH_ECWRAP [boolean] - Use EC wrap for encryption/decryption
#  XT_WITH_VERIFY_ASSERTIONS [boolean] - Verify assertions during decryption
#  XT_WITH_ASSERTIONS [string] - Path to assertions file, or JSON encoded as string
#  XT_WITH_ASSERTION_VERIFICATION_KEYS [string] - Path to assertion verification private key file
#  XT_WITH_ATTRIBUTES [string] - Attributes to be used for encryption
#  XT_WITH_MIME_TYPE [string] - MIME type for the encrypted file
#  XT_WITH_TARGET_MODE [string] - Target spec mode for the encrypted file
#  XT_WITH_KAS_ALLOWLIST [string] - Comma separated KAS allowlist for decrypt
#  XT_WITH_IGNORE_KAS_ALLOWLIST [boolean] - Disable the KAS allowlist for decrypt
#  CLIENTID [string] - Override OIDC client ID (default: opentdf)
#  CLIENTSECRET [string] - Override OIDC client secret (default: secret)
#
# Rejected with an error (not silently ignored): XT_WITH_DPOP,
# XT_WITH_ECDSA_BINDING, XT_WITH_PLAINTEXT_POLICY.
#
# Driver-only knobs (see driver.mjs): XT_WEB_BROWSER, XT_WEB_HEADED,
# XT_WEB_DEBUG.
#
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

# lib_at_least MAJOR MINOR: is the bundled @opentdf/sdk >= MAJOR.MINOR?
lib_at_least() {
  local major=$1 minor=$2
  jq -re .version "$SCRIPT_DIR/features.json" | awk -F. -v M="$major" -v m="$minor" '{ if ($1 > M || ($1 == M && $2 >= m)) exit 0; else exit 1; }'
  return $?
}

# has_algorithm REGEX: does PUBLIC_KEY_ALGORITHMS contain a match?
has_algorithm() {
  local pattern=$1
  jq -re --arg re "$pattern" '.publicKeyAlgorithms | map(select(test($re; "i"))) | length > 0' "$SCRIPT_DIR/features.json" >/dev/null
  return $?
}

if [[ "$1" == "supports" ]]; then
  if [[ ! -f "$SCRIPT_DIR/features.json" ]]; then
    echo "features.json missing; was this directory staged by stage.sh?"
    exit 1
  fi
  set -o pipefail
  # The js shim answers most of these by grepping `@opentdf/ctl help`. The
  # flags it greps for all shipped in the same release as the library
  # capability behind them, so the library version answers the same
  # question here. Releases before 0.4.0 are not supported by this flavour.
  case "$2" in
    assertions | assertion_verification | autoconfigure | ns_grants | hexaflexible | kasallowlist)
      lib_at_least 0 4
      exit $?
      ;;
    ecwrap)
      # Same gate as the js shim: earlier releases used an older salt.
      lib_at_least 0 5
      exit $?
      ;;
    hexless)
      jq -re .tdfSpecVersion "$SCRIPT_DIR/features.json" | awk -F. '{ if ($1 > 4 || ($1 == 4 && $2 >= 3)) exit 0; else exit 1; }'
      exit $?
      ;;
    key_management)
      lib_at_least 0 8
      exit $?
      ;;
    obligations)
      lib_at_least 0 6
      exit $?
      ;;
    attribute_traversal)
      lib_at_least 0 9
      exit $?
      ;;
    multikao)
      # DSPX-3379, shipped in web-sdk 0.20.0.
      lib_at_least 0 20
      exit $?
      ;;
    mechanism-mlkem)
      has_algorithm '^mlkem:768$'
      exit $?
      ;;
    mechanism-xwing)
      has_algorithm 'xwing'
      exit $?
      ;;
    dpop | dpop_nonce_challenge)
      # The library does DPoP itself, but the driver does not yet plumb
      # XT_WITH_DPOP / XT_WITH_DPOP_KEY through to it.
      echo "dpop is not wired into the web driver yet"
      exit 1
      ;;
    gmac_root_rejected)
      # See the js shim: not probeable, the fix adds no surface to detect.
      echo "gmac_root_rejected is not probeable: the fix adds no CLI surface"
      exit 1
      ;;
    chunky | zip64-at-2gib)
      # Library behaviour that predates any version we test; see the js shim.
      exit 0
      ;;
    *)
      echo "Unknown feature: $2"
      exit 2
      ;;
  esac
fi

XTEST_DIR=$SCRIPT_DIR
while [[ "$XTEST_DIR" != "/" ]]; do
  if [[ -f "$XTEST_DIR/pyproject.toml" ]] && grep -q 'name = "xtest"' "$XTEST_DIR/pyproject.toml"; then
    break
  fi
  XTEST_DIR=$(dirname "$XTEST_DIR")
done

if [[ "$XTEST_DIR" = "/" ]]; then
  echo "xtest root (pyproject.toml with name = \"xtest\") not found."
  exit 1
fi

# Capture any caller-set overrides before test.env unconditionally resets them.
_pre_clientid="${CLIENTID:-}"
_pre_clientsecret="${CLIENTSECRET:-}"

set -a
# shellcheck disable=SC1091
source "$XTEST_DIR"/test.env
set +a

# Restore caller overrides (e.g. from pytest monkeypatch for DPoP client).
[[ -n "$_pre_clientid" ]] && export CLIENTID="$_pre_clientid"
[[ -n "$_pre_clientsecret" ]] && export CLIENTSECRET="$_pre_clientsecret"

case "$1" in
  encrypt | decrypt) ;;
  *)
    echo "Incorrect argument provided"
    exit 1
    ;;
esac

src_file=$(realpath "$2")
dst_file=$3
if [[ "$dst_file" != /dev/null ]]; then
  dst_file=$(realpath "$(dirname "$3")")/$(basename "$3")
fi

# Relative XT_WITH_* paths are relative to the caller, not to SCRIPT_DIR.
for v in XT_WITH_ATTRIBUTES XT_WITH_ASSERTIONS XT_WITH_ASSERTION_VERIFICATION_KEYS; do
  if [[ -n "${!v}" && -f "${!v}" ]]; then
    export "$v=$(realpath "${!v}")"
  fi
done

exec node "$SCRIPT_DIR/driver.mjs" "$1" "$src_file" "$dst_file"
