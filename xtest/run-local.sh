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
#   LOG_LEVEL             Log level for all services (default: debug)
#   LOG_TYPE              Log format type (default: json)
#   SKIP_KAS_START        Set to "true" to skip starting additional KAS instances

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Configuration
PLATFORM_DIR="${PLATFORM_DIR:-$(cd "${TESTS_DIR}/../platform" && pwd)}"
START_KAS_INSTANCES="${START_KAS_INSTANCES:-alpha beta gamma delta km1 km2}"
LOG_LEVEL="${LOG_LEVEL:-debug}"
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
KM1_ROOT_KEY="${OT_ROOT_KEY:-a8c4824daafcfa38ed0d13002e92b08720e6c4fcee67d52e954c1a6e045907d1}"
KM2_ROOT_KEY="${OT_ROOT_KEY2:-a8c4824daafcfa38ed0d13002e92b08720e6c4fcee67d52e954c1a6e045907d1}"

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

# Check if platform is running, start it if not
PLATFORM_LOG_FILE="${PLATFORM_DIR}/logs/kas-main.log"

if ! curl -s http://localhost:8080/healthz >/dev/null 2>&1; then
  echo "Platform is not running. Starting platform..."
  echo ""

  cd "${PLATFORM_DIR}"

  # Check if keys exist, if not run init-temp-keys.sh
  if [[ ! -f kas-private.pem ]] || [[ ! -f kas-ec-private.pem ]]; then
    echo "Generating temporary keys..."
    .github/scripts/init-temp-keys.sh
  fi

  # Check if docker compose is running
  if ! docker compose ps | grep -q "postgres.*Up"; then
    echo "Starting docker compose services..."
    docker compose up -d --wait

    echo "Provisioning Keycloak..."
    go run ./service provision keycloak

    echo "Provisioning fixtures..."
    go run ./service provision fixtures
  fi

  # Load extra keys and configure opentdf.yaml
  echo "Configuring platform with extra keys and EC support..."
  EXTRA_KEYS_FILE="${TESTS_DIR}/xtest/extra-keys.json"

  if [[ ! -f opentdf.yaml ]]; then
    if [[ -f opentdf-dev.yaml ]]; then
      cp opentdf-dev.yaml opentdf.yaml
    else
      echo "Error: No opentdf.yaml or opentdf-dev.yaml found"
      exit 1
    fi
  fi

  # Add extra keys from extra-keys.json
  if [[ -f "${EXTRA_KEYS_FILE}" ]]; then
    keyring='[{"kid":"ec1","alg":"ec:secp256r1"},{"kid":"r1","alg":"rsa:2048"}]'
    keys='[{"kid":"e1","alg":"ec:secp256r1","private":"kas-ec-private.pem","cert":"kas-ec-cert.pem"},{"kid":"ec1","alg":"ec:secp256r1","private":"kas-ec-private.pem","cert":"kas-ec-cert.pem"},{"kid":"r1","alg":"rsa:2048","private":"kas-private.pem","cert":"kas-cert.pem"}]'

    while IFS= read -r key_json; do
      alg="$(jq -r '.alg' <<< "${key_json}")"
      private_pem="$(jq -r '.privateKey' <<< "${key_json}")"
      cert_pem="$(jq -r '.cert' <<< "${key_json}")"
      kid="$(jq -r '.kid' <<< "${key_json}")"

      if [[ ! "${kid}" =~ ^[-0-9a-zA-Z_]+$ ]]; then
        echo "Error: Invalid kid: ${kid}"
        exit 1
      fi

      private_path="${kid}.pem"
      cert_path="${kid}-cert.pem"

      echo "${private_pem}" >"${private_path}"
      echo "${cert_pem}" >"${cert_path}"
      chmod a+r "${private_path}" "${cert_path}"

      key_obj="$(jq '{kid, alg, private: $private, cert: $cert}' --arg private "${private_path}" --arg cert "${cert_path}" <<< "${key_json}")"
      keys="$(jq '. + [$key_obj]' --argjson key_obj "${key_obj}" <<< "${keys}")"

      keyring_obj="$(jq '{kid, alg}' <<< "${key_json}")"
      keyring="$(jq '. + [$keyring_obj]' --argjson keyring_obj "${keyring_obj}" <<< "${keyring}")"
    done < <(jq -c '.[]' < "${EXTRA_KEYS_FILE}")

    yq_command="$(printf '(.services.kas.keyring = %s) | (.server.cryptoProvider.standard.keys = %s)' "${keyring}" "${keys}")"
    yq e "${yq_command}" -i opentdf.yaml
  fi

  # Enable EC TDF support
  yq e '.services.kas.ec_tdf_enabled = true' -i opentdf.yaml

  # Configure logging
  yq e "(.logger.level = \"${LOG_LEVEL}\") | (.logger.type = \"${LOG_TYPE}\")" -i opentdf.yaml

  # Start platform using start-platform.sh
  echo "Starting platform server..."
  LOG_LEVEL="${LOG_LEVEL}" LOG_TYPE="${LOG_TYPE}" test/local/start-platform.sh &

  # Wait for platform to be ready
  for i in {1..30}; do
    if curl -s http://localhost:8080/healthz >/dev/null 2>&1; then
      echo "✓ Platform is ready"
      PLATFORM_STARTED=true
      break
    fi
    sleep 2
  done

  if [[ "${PLATFORM_STARTED}" == "false" ]]; then
    echo "Error: Platform did not become ready"
    exit 1
  fi

  cd "${SCRIPT_DIR}"
else
  echo "✓ Platform is already running"
fi

if [[ ! -f "${PLATFORM_LOG_FILE}" ]]; then
  echo "Warning: Platform log file not found: ${PLATFORM_LOG_FILE}"
  echo "Audit log assertions will be disabled."
  echo ""
  PLATFORM_LOG_FILE=""
else
  echo "  Log file: ${PLATFORM_LOG_FILE}"
fi

echo ""

# Start additional KAS instances if needed
declare -a KAS_LOG_FILES=()
declare -a KAS_STARTED_PORTS=()
PLATFORM_STARTED=false

# Ensure logs directory exists
mkdir -p "${PLATFORM_DIR}/logs"

cleanup_all() {
  echo ""
  echo "Cleaning up..."

  # Clean up KAS instances
  if [[ ${#KAS_STARTED_PORTS[@]} -gt 0 ]]; then
    echo "Cleaning up KAS instances on ports: ${KAS_STARTED_PORTS[*]}"
    for port in "${KAS_STARTED_PORTS[@]}"; do
      echo "Looking for process on port ${port}..."
      pid=$(lsof -t -i:"${port}" || true)
      if [[ -n "${pid}" ]]; then
        echo "Stopping KAS on port ${port} (PID: ${pid})"
        kill "${pid}" || true
        sleep 1
        if kill -0 "${pid}" 2>/dev/null; then
          echo "  Force killing PID: ${pid}"
          kill -9 "${pid}" || true
        fi
      else
        echo "No process found on port ${port}"
      fi
    done
  fi

  # Clean up platform if we started it
  if [[ "${PLATFORM_STARTED}" == "true" ]]; then
    echo "Cleaning up platform..."
    pid=$(lsof -t -i:8080 || true)
    if [[ -n "${pid}" ]]; then
      echo "Stopping platform on port 8080 (PID: ${pid})"
      kill "${pid}" || true
      sleep 1
      if kill -0 "${pid}" 2>/dev/null; then
        echo "  Force killing PID: ${pid}"
        kill -9 "${pid}" || true
      fi
    fi
  fi
}

# Set up cleanup trap
trap cleanup_all EXIT INT TERM

if [[ "${SKIP_KAS_START}" != "true" ]]; then
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

    # Determine if this is a key management KAS
    extra_args=""
    if [[ "${kas_name}" == "km1" ]]; then
      extra_args="--key-management=true --ec-tdf-enabled=true --root-key=${KM1_ROOT_KEY}"
    elif [[ "${kas_name}" == "km2" ]]; then
      extra_args="--key-management=true --ec-tdf-enabled=true --root-key=${KM2_ROOT_KEY}"
    fi

    log_file="${PLATFORM_DIR}/logs/kas-${kas_name}.log"

    # Create log file so it can be tailed immediately
    touch "${log_file}"

    echo "Starting KAS ${kas_name} on port ${port}..."
    echo "  Log file: ${log_file}"

    # Start KAS in background
    # Redirect output to log file so we can see any startup errors from start-kas.sh itself
    (
      cd "${PLATFORM_DIR}"
      LOG_LEVEL="${LOG_LEVEL}" LOG_TYPE="${LOG_TYPE}" \
        test/local/start-kas.sh "${kas_name}" "${port}" ${extra_args} >>"${log_file}" 2>&1
    ) &

    # Wait for KAS to be ready
    for i in {1..30}; do
      if curl -s "http://localhost:${port}/healthz" >/dev/null 2>&1; then
        echo "  ✓ KAS ${kas_name} ready"
        KAS_LOG_FILES+=("${kas_name}:${log_file}")
        KAS_STARTED_PORTS+=("${port}")
        break
      fi
      sleep 1
      if [[ $i -eq 30 ]]; then
        echo "  ✗ KAS ${kas_name} failed to start"
        echo ""
        echo "=== Last 50 lines of ${log_file} ==="
        if [[ -f "${log_file}" ]]; then
          tail -n 50 "${log_file}"
        else
          echo "Log file not found: ${log_file}"
        fi
        echo "=== End of log ==="
        exit 1
      fi
    done
  done

  echo ""
fi

# Export environment variables for pytest
export PLATFORM_DIR="${PLATFORM_DIR}"
[[ -n "${PLATFORM_LOG_FILE}" ]] && export PLATFORM_LOG_FILE="${PLATFORM_LOG_FILE}"
export OT_ROOT_KEY="${KM1_ROOT_KEY}"
export OT_ROOT_KEY2="${KM2_ROOT_KEY}"

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
