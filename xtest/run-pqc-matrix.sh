#!/usr/bin/env bash
# Run the PQC X-Wing test matrix: SDK variant x backend variant.
#
# Prerequisites:
#   1. otdf-sdk-mgr and otdf-local installed (uv tool install --editable)
#   2. Docker running (for Keycloak + Postgres)
#
# Usage:
#   ./run-pqc-matrix.sh              # Full 3x3 matrix
#   ./run-pqc-matrix.sh --build      # Build SDK variants only (no tests)
#   ./run-pqc-matrix.sh --diagonal   # Only test matching SDK/backend pairs
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# --- Variant definitions (override with env vars) ---
VARIANTS=(gemini enhanced codex)
PLATFORM_DIRS=(
  "${PQC_GEMINI_DIR:-$HOME/Documents/GitHub/post-quantum-hybrid-gemini-2026-03-dm/platform}"
  "${PQC_ENHANCED_DIR:-$HOME/Documents/GitHub/post-quantum-enhanced-2026-03-dm/platform}"
  "${PQC_CODEX_DIR:-$HOME/Documents/GitHub/post-quantum-hybrid-codex-2026-03-dm/platform}"
)

# --- Options ---
BUILD_ONLY=false
DIAGONAL_ONLY=false
PYTEST_ARGS=()

for arg in "$@"; do
  case "$arg" in
    --build) BUILD_ONLY=true ;;
    --diagonal) DIAGONAL_ONLY=true ;;
    *) PYTEST_ARGS+=("$arg") ;;
  esac
done

# --- Phase 1: Build all SDK variants ---
echo "=== Phase 1: Building SDK variants ==="
for i in "${!VARIANTS[@]}"; do
  variant="${VARIANTS[$i]}"
  platform_dir="${PLATFORM_DIRS[$i]}"
  if [ ! -d "$platform_dir" ]; then
    echo "WARNING: Platform dir not found: $platform_dir (skipping $variant)"
    continue
  fi
  echo "--- Building $variant from $platform_dir ---"
  otdf-sdk-mgr install variant "$variant" "$platform_dir"
done

if $BUILD_ONLY; then
  echo "=== Build complete. SDK variants in sdk/go/dist/ ==="
  ls -la sdk/go/dist/
  exit 0
fi

# --- Phase 2: Run test matrix ---
echo ""
echo "=== Phase 2: Running test matrix ==="
mkdir -p results

OTDF_LOCAL_DIR="$SCRIPT_DIR/../otdf-local"
PASS=0
FAIL=0
SKIP=0
SUMMARY=""

for bi in "${!VARIANTS[@]}"; do
  backend="${VARIANTS[$bi]}"
  backend_dir="${PLATFORM_DIRS[$bi]}"

  if [ ! -d "$backend_dir" ]; then
    echo "WARNING: Backend dir not found: $backend_dir (skipping)"
    SKIP=$((SKIP + 1))
    continue
  fi

  echo ""
  echo "=== Starting backend: $backend ==="
  export OTDF_LOCAL_PLATFORM_DIR="$backend_dir"

  (cd "$OTDF_LOCAL_DIR" && uv run otdf-local down 2>/dev/null) || true
  if ! (cd "$OTDF_LOCAL_DIR" && uv run otdf-local up); then
    echo "ERROR: Failed to start backend $backend"
    SUMMARY+="  BACKEND-FAIL $backend"$'\n'
    SKIP=$((SKIP + ${#VARIANTS[@]}))
    continue
  fi

  for si in "${!VARIANTS[@]}"; do
    sdk="${VARIANTS[$si]}"

    # Diagonal mode: skip non-matching pairs
    if $DIAGONAL_ONLY && [ "$si" != "$bi" ]; then
      continue
    fi

    log_file="results/${sdk}-on-${backend}.log"
    echo ""
    echo "--- Testing SDK=$sdk Backend=$backend ---"

    set -a && source test.env && set +a

    if uv run pytest test_tdfs.py -k xwing \
        --sdks "go:$sdk" \
        -v --tb=short \
        "${PYTEST_ARGS[@]}" \
        2>&1 | tee "$log_file"; then
      result="PASS"
      PASS=$((PASS + 1))
    else
      result="FAIL"
      FAIL=$((FAIL + 1))
    fi
    SUMMARY+="  $result  SDK=$sdk  Backend=$backend"$'\n'
  done
done

# Shut down services
(cd "$OTDF_LOCAL_DIR" && uv run otdf-local down 2>/dev/null) || true

echo ""
echo "============================================"
echo "  PQC Matrix Results"
echo "============================================"
echo "$SUMMARY"
echo "  Total: $((PASS + FAIL + SKIP))  Pass: $PASS  Fail: $FAIL  Skip: $SKIP"
echo ""
echo "  Logs in: $SCRIPT_DIR/results/"
echo "============================================"
