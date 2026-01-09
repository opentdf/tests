#!/usr/bin/env bash
# Tmux-based development environment for OpenTDF integration testing
# Manages multiple interlocking services with live log monitoring
#
# Usage:
#   ./tmux-dev.sh [options]
#
# Options:
#   --minimal      Start minimal environment (docker + platform)
#   --standard     Start standard environment (docker + platform + 2 KAS)
#   --full         Start full environment (all services) [default]
#   --attach-only  Attach to existing session without starting
#   --stop         Stop session and cleanup all services
#   -h, --help     Show this help message
#
# Examples:
#   ./tmux-dev.sh                # Start full environment
#   ./tmux-dev.sh --minimal      # Start minimal environment
#   ./tmux-dev.sh --attach-only  # Reattach to existing session
#   ./tmux-dev.sh --stop         # Stop and cleanup

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLATFORM_DIR="${PLATFORM_DIR:-$(cd "${TESTS_DIR}/../platform" && pwd)}"

SESSION_NAME="opentdf-dev"
MODE="full"
ATTACH_ONLY=false
STOP_SESSION=false
DETACHED=false

# KAS port mappings
declare -A KAS_PORTS=(
  ["alpha"]="8181"
  ["beta"]="8282"
  ["gamma"]="8383"
  ["delta"]="8484"
  ["km1"]="8585"
  ["km2"]="8686"
)

# KAS root keys
KM1_ROOT_KEY="${OT_ROOT_KEY:-a8c4824daafcfa38ed0d13002e92b08720e6c4fcee67d52e954c1a6e045907d1}"
KM2_ROOT_KEY="${OT_ROOT_KEY2:-a8c4824daafcfa38ed0d13002e92b08720e6c4fcee67d52e954c1a6e045907d1}"

# Logging configuration
LOG_LEVEL="${LOG_LEVEL:-audit}"
LOG_TYPE="${LOG_TYPE:-json}"
LOG_DIR="${PLATFORM_DIR}/logs"

#################
# Functions
#################

show_help() {
  cat <<EOF
Tmux-based development environment for OpenTDF integration testing

Usage: $0 [options]

Options:
  --minimal      Start minimal environment (docker + platform)
  --standard     Start standard environment (docker + platform + 2 KAS)
  --full         Start full environment (all services) [default]
  --attach-only  Attach to existing session without starting
  --detached     Create session without attaching (useful for testing/automation)
  --stop         Stop session and cleanup all services
  -h, --help     Show this help message

Examples:
  $0                # Start full environment
  $0 --minimal      # Start minimal environment
  $0 --attach-only  # Reattach to existing session
  $0 --stop         # Stop and cleanup

Window Layout:
  control     - Status dashboard with service health
  docker      - Docker Compose logs
  platform    - Platform main service (port 8080)
  kas-alpha   - KAS instance (port 8181)
  kas-beta    - KAS instance (port 8282)
  kas-gamma   - KAS instance (port 8383)
  kas-delta   - KAS instance (port 8484)
  kas-km1     - Key management KAS (port 8585)
  kas-km2     - Key management KAS (port 8686)
  tests       - Test runner shell

Navigation:
  Ctrl-b <number>  - Switch to window by index
  Ctrl-b '         - Switch to window by name (e.g., 'tests')
  Ctrl-b w         - Window list (interactive)
  Ctrl-b n/p       - Next/previous window
  Ctrl-b d         - Detach from session
  Ctrl-b :         - Command prompt

Notes:
  - Running this script from within an active tmux session will prompt you
    to switch sessions rather than creating nested tmux sessions
  - Use --attach-only from within tmux to quickly switch to opentdf-dev
EOF
}

check_dependencies() {
  local missing=()

  for cmd in tmux docker curl lsof yq; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      missing+=("$cmd")
    fi
  done

  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "Error: Missing required commands: ${missing[*]}"
    echo ""
    if command -v brew >/dev/null 2>&1; then
      echo "Install with: brew install ${missing[*]}"
    elif command -v apt-get >/dev/null 2>&1; then
      echo "Install with: sudo apt-get install ${missing[*]}"
    fi
    exit 1
  fi
}

check_existing_session() {
  if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
    return 0
  else
    return 1
  fi
}

check_nested_tmux() {
  if [[ -n "${TMUX:-}" ]]; then
    return 0  # We are inside tmux
  else
    return 1  # Not inside tmux
  fi
}

handle_nested_tmux() {
  local current_session
  current_session=$(tmux display-message -p '#S' 2>/dev/null)

  echo "Warning: You are already inside a tmux session: '${current_session}'"
  echo ""
  echo "Running tmux inside tmux (nested sessions) is not recommended."
  echo ""

  if check_existing_session; then
    echo "The '${SESSION_NAME}' session already exists."
    echo ""
    echo "Options:"
    echo "  1. Detach from current session and attach to '${SESSION_NAME}'"
    echo "  2. Switch to '${SESSION_NAME}' session (switch-client)"
    echo "  3. Cancel"
    echo ""
    read -p "Choose [1/2/3]: " -n 1 -r
    echo ""

    case $REPLY in
      1)
        echo "Detaching and reattaching..."
        tmux detach-client
        exec tmux attach-session -t "${SESSION_NAME}"
        ;;
      2)
        echo "Switching to '${SESSION_NAME}' session..."
        exec tmux switch-client -t "${SESSION_NAME}"
        ;;
      *)
        echo "Cancelled."
        exit 0
        ;;
    esac
  else
    echo "Options:"
    echo "  1. Detach from current session and start '${SESSION_NAME}'"
    echo "  2. Cancel (recommended: detach manually with Ctrl-b d, then run this script)"
    echo ""
    read -p "Choose [1/2]: " -n 1 -r
    echo ""

    case $REPLY in
      1)
        echo "Detaching from current session..."
        tmux detach-client
        # Re-exec the script outside tmux
        exec "$0" "$@"
        ;;
      *)
        echo "Cancelled."
        echo ""
        echo "To use this script properly:"
        echo "  1. Detach from current session: Ctrl-b d"
        echo "  2. Run: $0 ${MODE:+--$MODE}"
        exit 0
        ;;
    esac
  fi
}

stop_session() {
  echo "=== Stopping OpenTDF Development Environment ==="

  if ! check_existing_session; then
    echo "No session '${SESSION_NAME}' found."
    exit 0
  fi

  echo "Killing tmux session: ${SESSION_NAME}"
  tmux kill-session -t "${SESSION_NAME}"

  echo "Cleaning up any remaining processes..."

  # Kill any remaining platform/KAS processes
  for port in 8080 8181 8282 8383 8484 8585 8686; do
    if lsof -Pi ":${port}" -sTCP:LISTEN -t >/dev/null 2>&1; then
      echo "Killing process on port ${port}"
      kill "$(lsof -t -i:${port})" 2>/dev/null || true
    fi
  done

  echo "Cleanup complete."
}

verify_platform_dir() {
  if [[ ! -d "${PLATFORM_DIR}" ]]; then
    echo "Error: Platform directory not found: ${PLATFORM_DIR}"
    echo "Set PLATFORM_DIR environment variable to point to your platform checkout"
    exit 1
  fi

  if [[ ! -f "${PLATFORM_DIR}/docker-compose.yaml" ]]; then
    echo "Error: docker-compose.yaml not found in ${PLATFORM_DIR}"
    exit 1
  fi
}

setup_log_directory() {
  mkdir -p "${LOG_DIR}"
}

create_control_window() {
  local window_name="control"

  tmux new-window -t "${SESSION_NAME}" -n "${window_name}"
  tmux send-keys -t "${SESSION_NAME}:${window_name}" \
    "cd '${SCRIPT_DIR}' && MODE='${MODE}' PLATFORM_DIR='${PLATFORM_DIR}' watch -n 2 -c ./tmux-control-panel.sh" C-m
}

start_docker_compose() {
  local window_name="docker"

  tmux new-window -t "${SESSION_NAME}" -n "${window_name}"

  # Check if docker compose is already running
  tmux send-keys -t "${SESSION_NAME}:${window_name}" \
    "cd '${PLATFORM_DIR}'" C-m

  tmux send-keys -t "${SESSION_NAME}:${window_name}" \
    "if docker compose ps | grep -q 'postgres.*Up'; then echo 'Docker Compose already running'; docker compose logs -f; else echo 'Starting Docker Compose...'; docker compose up -d --wait && echo 'Docker Compose started' && docker compose logs -f; fi" C-m
}

start_platform() {
  local window_name="platform"

  tmux new-window -t "${SESSION_NAME}" -n "${window_name}"
  tmux send-keys -t "${SESSION_NAME}:${window_name}" \
    "cd '${PLATFORM_DIR}'" C-m

  # Check if platform is already running
  tmux send-keys -t "${SESSION_NAME}:${window_name}" \
    "if curl -s http://localhost:8080/healthz >/dev/null 2>&1; then echo 'Platform already running on port 8080'; echo 'Tailing logs...'; tail -f '${LOG_DIR}/kas-main.log'; else echo 'Starting platform...'; LOG_LEVEL='${LOG_LEVEL}' LOG_TYPE='${LOG_TYPE}' test/local/start-platform.sh --tmux; fi" C-m
}

start_kas_instance() {
  local kas_name="$1"
  local port="${KAS_PORTS[$kas_name]}"
  local window_name="kas-${kas_name}"

  # Extra args for key management KAS
  local extra_args=""
  if [[ "${kas_name}" == "km1" ]]; then
    extra_args="--key-management=true --root-key=${KM1_ROOT_KEY}"
  elif [[ "${kas_name}" == "km2" ]]; then
    extra_args="--key-management=true --root-key=${KM2_ROOT_KEY}"
  fi

  tmux new-window -t "${SESSION_NAME}" -n "${window_name}"
  tmux send-keys -t "${SESSION_NAME}:${window_name}" \
    "cd '${PLATFORM_DIR}'" C-m

  # Check if KAS is already running
  tmux send-keys -t "${SESSION_NAME}:${window_name}" \
    "if curl -s http://localhost:${port}/healthz >/dev/null 2>&1; then echo 'KAS ${kas_name} already running on port ${port}'; echo 'Tailing logs...'; tail -f '${LOG_DIR}/kas-${kas_name}.log'; else echo 'Starting KAS ${kas_name}...'; LOG_LEVEL='${LOG_LEVEL}' LOG_TYPE='${LOG_TYPE}' test/local/start-kas.sh '${kas_name}' '${port}' ${extra_args} --tmux; fi" C-m
}

create_test_window() {
  local window_name="tests"

  tmux new-window -t "${SESSION_NAME}" -n "${window_name}"
  tmux send-keys -t "${SESSION_NAME}:${window_name}" \
    "cd '${SCRIPT_DIR}'" C-m

  tmux send-keys -t "${SESSION_NAME}:${window_name}" \
    "# Test runner shell" C-m
  tmux send-keys -t "${SESSION_NAME}:${window_name}" \
    "# Run tests with: pytest test_tdfs.py" C-m
  tmux send-keys -t "${SESSION_NAME}:${window_name}" \
    "# Or use: ./run-local.sh test_tdfs.py" C-m
  tmux send-keys -t "${SESSION_NAME}:${window_name}" \
    "echo ''" C-m
}

export_env_vars() {
  # Export environment variables to tmux session
  tmux setenv -t "${SESSION_NAME}" PLATFORM_DIR "${PLATFORM_DIR}"
  tmux setenv -t "${SESSION_NAME}" TESTS_DIR "${TESTS_DIR}"
  tmux setenv -t "${SESSION_NAME}" LOG_DIR "${LOG_DIR}"
  tmux setenv -t "${SESSION_NAME}" LOG_LEVEL "${LOG_LEVEL}"
  tmux setenv -t "${SESSION_NAME}" LOG_TYPE "${LOG_TYPE}"
  tmux setenv -t "${SESSION_NAME}" TMUX_MODE "true"
}

start_environment() {
  echo "=== Starting OpenTDF Development Environment ==="
  echo "Mode: ${MODE}"
  echo "Platform: ${PLATFORM_DIR}"
  echo ""

  verify_platform_dir
  check_dependencies
  setup_log_directory

  # Create new tmux session (detached)
  tmux new-session -d -s "${SESSION_NAME}" -n "init"

  # Export environment variables
  export_env_vars

  echo "Creating windows..."

  # Create control window
  create_control_window

  # Create docker window
  start_docker_compose

  # Wait for docker compose to be ready
  echo "Waiting for Docker Compose services..."
  sleep 3

  # Create platform window
  start_platform

  if [[ "${MODE}" == "minimal" ]]; then
    # Minimal mode: only docker + platform
    echo "Minimal mode: Starting docker + platform only"
  elif [[ "${MODE}" == "standard" ]]; then
    # Standard mode: docker + platform + 2 KAS
    echo "Standard mode: Starting docker + platform + 2 KAS instances"
    start_kas_instance "alpha"
    start_kas_instance "beta"
  else
    # Full mode: all services
    echo "Full mode: Starting all services"
    start_kas_instance "alpha"
    start_kas_instance "beta"
    start_kas_instance "gamma"
    start_kas_instance "delta"
    start_kas_instance "km1"
    start_kas_instance "km2"
  fi

  # Create test window
  create_test_window

  # Kill the init window
  tmux kill-window -t "${SESSION_NAME}:init"

  # Select control window
  tmux select-window -t "${SESSION_NAME}:control"

  echo ""
  echo "Environment started!"

  if [[ "${DETACHED}" == "true" ]]; then
    echo ""
    echo "Session '${SESSION_NAME}' created in detached mode."
    echo ""
    echo "To attach to the session:"
    echo "  tmux attach-session -t ${SESSION_NAME}"
    echo ""
    echo "Or use:"
    echo "  ./tmux-dev.sh --attach-only"
    echo ""
    echo "To stop:"
    echo "  ./tmux-dev.sh --stop"
  else
    echo "Attaching to session '${SESSION_NAME}'..."
    echo ""
    echo "Use 'Ctrl-b d' to detach from session"
    echo "Use './tmux-dev.sh --attach-only' to reattach"
    echo "Use './tmux-dev.sh --stop' to stop and cleanup"
    echo ""
    sleep 2

    # Attach to session
    tmux attach-session -t "${SESSION_NAME}"
  fi
}

#################
# Main
#################

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --minimal)
      MODE="minimal"
      shift
      ;;
    --standard)
      MODE="standard"
      shift
      ;;
    --full)
      MODE="full"
      shift
      ;;
    --attach-only)
      ATTACH_ONLY=true
      shift
      ;;
    --detached)
      DETACHED=true
      shift
      ;;
    --stop)
      STOP_SESSION=true
      shift
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      show_help
      exit 1
      ;;
  esac
done

# Handle --stop
if [[ "${STOP_SESSION}" == "true" ]]; then
  stop_session
  exit 0
fi

# Handle --attach-only
if [[ "${ATTACH_ONLY}" == "true" ]]; then
  if check_existing_session; then
    # If already in tmux, use switch-client instead of attach
    if check_nested_tmux; then
      echo "Switching to existing session '${SESSION_NAME}'..."
      exec tmux switch-client -t "${SESSION_NAME}"
    else
      echo "Attaching to existing session '${SESSION_NAME}'..."
      tmux attach-session -t "${SESSION_NAME}"
    fi
  else
    echo "Error: No session '${SESSION_NAME}' found."
    echo "Start a new session with: ./tmux-dev.sh"
    exit 1
  fi
  exit 0
fi

# Check if we're already inside a tmux session (skip if --detached)
if [[ "${DETACHED}" != "true" ]] && check_nested_tmux; then
  handle_nested_tmux
  # If we get here, user chose to cancel or we switched sessions
  exit 0
fi

# Check for existing session
if check_existing_session; then
  echo "Session '${SESSION_NAME}' already exists."
  echo ""
  read -p "Do you want to (a)ttach, (k)ill and restart, or (c)ancel? [a/k/c]: " -n 1 -r
  echo ""

  case $REPLY in
    a|A)
      echo "Attaching to existing session..."
      tmux attach-session -t "${SESSION_NAME}"
      exit 0
      ;;
    k|K)
      echo "Killing existing session and restarting..."
      stop_session
      sleep 2
      ;;
    *)
      echo "Cancelled."
      exit 0
      ;;
  esac
fi

# Start new environment
start_environment
