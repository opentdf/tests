#!/usr/bin/env bash
# Wrapper script to run xtest locally with audit log collection
# This mimics the CI environment by:
# 1. Ensuring platform services are running with log capture
# 2. Starting additional KAS instances if needed
# 3. Exporting log file paths as environment variables
# 4. Running pytest with those environment variables
#
# Usage:
#   ./run-local.sh [pytest-args]
#
# Examples:
#   ./run-local.sh test_abac.py          # Run ABAC tests with all KAS instances
#   ./run-local.sh test_tdfs.py -v       # Run TDF tests verbosely
#   ./run-local.sh --focus go            # Run only Go SDK tests
#
# Environment Variables:
#   PLATFORM_DIR          Path to platform repo (default: ../../platform)
#   START_KAS_INSTANCES   Space-separated KAS names to start (default: "alpha beta gamma delta km1 km2")
#   LOG_LEVEL             Log level for all services (default: audit)
#   LOG_TYPE              Log format type (default: json)
#   SKIP_KAS_START        Set to "true" to skip starting additional KAS instances

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Configuration
PLATFORM_DIR="${PLATFORM_DIR:-$(cd "${TESTS_DIR}/../platform" && pwd)}"
START_KAS_INSTANCES="${START_KAS_INSTANCES:-alpha beta gamma delta km1 km2}"
LOG_LEVEL="${LOG_LEVEL:-audit}"
LOG_TYPE="${LOG_TYPE:-json}"
SKIP_KAS_START="${SKIP_KAS_START:-false}"

# KAS port mappings (matching CI configuration)
declare -A KAS_PORTS=(
  ["alpha"]="8181"
  ["beta"]="8282"
  ["gamma"]="8383"
  ["delta"]="8484"
  ["km1"]="8585"
  ["km2"]="8686"
)

# KAS root keys for key management
KM1_ROOT_KEY="${OT_ROOT_KEY:-Sk5OQ1dLQWExRkMyelFWdz09}"  # Base64 encoded test key
KM2_ROOT_KEY="${OT_ROOT_KEY2:-U2s1T1EzZExRV0V4UmtNMmVsRldkejA5}"  # Different test key

echo "=== OpenTDF xtest Local Runner ==="
echo ""

# Verify platform directory exists
if [[ ! -d "${PLATFORM_DIR}" ]]; then
  echo "Error: Platform directory not found: ${PLATFORM_DIR}"
  echo "Set PLATFORM_DIR environment variable to point to your platform checkout"
  exit 1
fi

echo "Platform directory: ${PLATFORM_DIR}"
echo "Tests directory: ${TESTS_DIR}"
echo ""

# Check if platform is running
PLATFORM_LOG_FILE="${PLATFORM_DIR}/logs/kas-main.log"
if ! curl -s http://localhost:8080/healthz >/dev/null 2>&1; then
  echo "Error: Platform is not running on port 8080"
  echo ""
  echo "Please start the platform first:"
  echo "  cd ${PLATFORM_DIR}"
  echo "  docker compose up -d --wait"
  echo "  go run ./service provision keycloak"
  echo "  go run ./service provision fixtures"
  echo "  LOG_LEVEL=${LOG_LEVEL} LOG_TYPE=${LOG_TYPE} test/local/start-platform.sh"
  echo ""
  exit 1
fi

if [[ ! -f "${PLATFORM_LOG_FILE}" ]]; then
  echo "Warning: Platform log file not found: ${PLATFORM_LOG_FILE}"
  echo "Platform may not have been started with log capture."
  echo "Audit log assertions will be disabled."
  echo ""
  PLATFORM_LOG_FILE=""
fi

echo "✓ Platform is running"
[[ -n "${PLATFORM_LOG_FILE}" ]] && echo "  Log file: ${PLATFORM_LOG_FILE}"
echo ""

# Start additional KAS instances if needed
declare -a KAS_LOG_FILES=()
declare -a KAS_PIDS=()

cleanup_kas() {
  echo ""
  echo "Cleaning up KAS instances..."
  for pid in "${KAS_PIDS[@]}"; do
    if kill -0 "${pid}" 2>/dev/null; then
      echo "Stopping KAS with PID: ${pid}"
      kill "${pid}" 2>/dev/null || true
    fi
  done
}

if [[ "${SKIP_KAS_START}" != "true" ]]; then
  trap cleanup_kas EXIT INT TERM

  for kas_name in ${START_KAS_INSTANCES}; do
    port="${KAS_PORTS[$kas_name]}"

    # Check if already running
    if curl -s "http://localhost:${port}/healthz" >/dev/null 2>&1; then
      echo "✓ KAS ${kas_name} already running on port ${port}"
      log_file="${PLATFORM_DIR}/logs/kas-${kas_name}.log"
      if [[ -f "${log_file}" ]]; then
        KAS_LOG_FILES+=("${kas_name}:${log_file}")
      fi
      continue
    fi

    # Check if port is in use by another process
    if lsof -Pi :${port} -sTCP:LISTEN -t >/dev/null 2>&1; then
      echo "  ✗ Port ${port} is already in use by another process"
      echo "     Run: kill \$(lsof -t -i:${port})"
      continue
    fi

    # Determine if this is a key management KAS
    extra_args=""
    if [[ "${kas_name}" == "km1" ]]; then
      extra_args="--key-management=true --root-key=${KM1_ROOT_KEY}"
    elif [[ "${kas_name}" == "km2" ]]; then
      extra_args="--key-management=true --root-key=${KM2_ROOT_KEY}"
    fi

    echo "Starting KAS ${kas_name} on port ${port}..."

    # Create temporary file for capturing startup output
    startup_log=$(mktemp)

    # Start KAS in background
    (
      cd "${PLATFORM_DIR}"
      LOG_LEVEL="${LOG_LEVEL}" LOG_TYPE="${LOG_TYPE}" \
        test/local/start-kas.sh "${kas_name}" "${port}" ${extra_args} >"${startup_log}" 2>&1
    ) &

    startup_pid=$!
    KAS_PIDS+=($startup_pid)

    # Wait for KAS to be ready
    kas_ready=false
    for i in {1..30}; do
      # Check if startup process failed
      if ! kill -0 ${startup_pid} 2>/dev/null; then
        echo "  ✗ KAS ${kas_name} startup process died"
        echo ""
        echo "  Startup output:"
        sed 's/^/    /' "${startup_log}"
        echo ""
        rm -f "${startup_log}"
        break
      fi

      if curl -s "http://localhost:${port}/healthz" >/dev/null 2>&1; then
        echo "  ✓ KAS ${kas_name} ready"
        log_file="${PLATFORM_DIR}/logs/kas-${kas_name}.log"
        KAS_LOG_FILES+=("${kas_name}:${log_file}")
        kas_ready=true
        rm -f "${startup_log}"
        break
      fi
      sleep 1
    done

    if [[ "${kas_ready}" != "true" ]]; then
      echo "  ✗ KAS ${kas_name} failed to start after 30 seconds"
      echo ""
      echo "  Startup output:"
      sed 's/^/    /' "${startup_log}"
      echo ""

      # Check log file if it exists
      log_file="${PLATFORM_DIR}/logs/kas-${kas_name}.log"
      if [[ -f "${log_file}" ]]; then
        echo "  Last 10 lines of KAS log:"
        tail -10 "${log_file}" | sed 's/^/    /'
        echo ""
      fi

      rm -f "${startup_log}"
      echo "  Hint: Check if platform is running and properly configured"
      exit 1
    fi
  done

  echo ""
fi

# Export environment variables for pytest
export PLATFORM_DIR="${PLATFORM_DIR}"
[[ -n "${PLATFORM_LOG_FILE}" ]] && export PLATFORM_LOG_FILE="${PLATFORM_LOG_FILE}"

# Export KAS log file paths
for entry in "${KAS_LOG_FILES[@]}"; do
  kas_name="${entry%%:*}"
  log_file="${entry#*:}"
  env_var="KAS_${kas_name^^}_LOG_FILE"
  export "${env_var}=${log_file}"
  echo "Export: ${env_var}=${log_file}"
done

echo ""
echo "=== Running pytest ==="
echo ""

cd "${SCRIPT_DIR}"

# Run pytest with provided arguments
if [[ $# -gt 0 ]]; then
  pytest "$@"
else
  # Default: run all tests with HTML report
  pytest -v --html=test-results/report.html --self-contained-html
fi

exit_code=$?

echo ""
if [[ ${exit_code} -eq 0 ]]; then
  echo "✓ Tests passed"
else
  echo "✗ Tests failed with exit code ${exit_code}"
fi

exit ${exit_code}
