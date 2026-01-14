#!/usr/bin/env bash
# Control panel for OpenTDF tmux development environment
# Displays service status, log paths, and useful commands
#
# This script is meant to be run with watch in tmux control window

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLATFORM_DIR="${PLATFORM_DIR:-$(cd "${TESTS_DIR}/../platform" && pwd 2>/dev/null)}"
LOG_DIR="${LOG_DIR:-${PLATFORM_DIR}/logs}"
MODE="${MODE:-full}"

# Color codes for output
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
BLUE="\033[0;34m"
BOLD="\033[1m"
RESET="\033[0m"

# Service definitions
declare -A SERVICES=(
  ["docker"]="Docker Compose:N/A:keycloak,postgres"
  ["platform"]="Platform Main:8080:http://localhost:8080/healthz"
  ["kas-alpha"]="KAS Alpha:8181:http://localhost:8181/healthz"
  ["kas-beta"]="KAS Beta:8282:http://localhost:8282/healthz"
  ["kas-gamma"]="KAS Gamma:8383:http://localhost:8383/healthz"
  ["kas-delta"]="KAS Delta:8484:http://localhost:8484/healthz"
  ["kas-km1"]="KAS KM1:8585:http://localhost:8585/healthz"
  ["kas-km2"]="KAS KM2:8686:http://localhost:8686/healthz"
)

check_service_status() {
  local service_key="$1"
  local service_info="${SERVICES[$service_key]}"
  local service_name=$(echo "$service_info" | cut -d: -f1)
  local port=$(echo "$service_info" | cut -d: -f2)
  local healthcheck=$(echo "$service_info" | cut -d: -f3)

  if [[ "$service_key" == "docker" ]]; then
    # Check docker compose
    if docker compose -f "${PLATFORM_DIR}/docker-compose.yaml" ps 2>/dev/null | grep -q "postgres.*Up"; then
      echo -e "  ${GREEN}✓${RESET} ${service_name}  (keycloak, postgres)"
    else
      echo -e "  ${RED}✗${RESET} ${service_name}  (not running)"
    fi
  else
    # Check HTTP service
    if curl -s -f "$healthcheck" >/dev/null 2>&1; then
      echo -e "  ${GREEN}✓${RESET} ${service_name}  (http://localhost:${port})"
    else
      echo -e "  ${RED}✗${RESET} ${service_name}  (http://localhost:${port})"
    fi
  fi
}

get_log_file() {
  local service_key="$1"

  case "$service_key" in
    platform)
      echo "${LOG_DIR}/kas-main.log"
      ;;
    kas-*)
      local kas_name="${service_key#kas-}"
      echo "${LOG_DIR}/kas-${kas_name}.log"
      ;;
    docker)
      echo "docker compose logs -f"
      ;;
    *)
      echo "N/A"
      ;;
  esac
}

show_service_status() {
  echo -e "${BOLD}Services Status:${RESET}"

  # Always show docker and platform
  check_service_status "docker"
  check_service_status "platform"

  # Show KAS instances based on mode
  if [[ "${MODE}" == "standard" ]]; then
    check_service_status "kas-alpha"
    check_service_status "kas-beta"
  elif [[ "${MODE}" == "full" ]]; then
    check_service_status "kas-alpha"
    check_service_status "kas-beta"
    check_service_status "kas-gamma"
    check_service_status "kas-delta"
    check_service_status "kas-km1"
    check_service_status "kas-km2"
  fi
}

show_log_files() {
  echo ""
  echo -e "${BOLD}Log Files:${RESET}"

  # Platform log
  local platform_log=$(get_log_file "platform")
  if [[ -f "${platform_log}" ]]; then
    echo -e "  Platform: ${BLUE}${platform_log}${RESET}"
  else
    echo -e "  Platform: ${YELLOW}${platform_log}${RESET} (not yet created)"
  fi

  # KAS logs based on mode
  if [[ "${MODE}" == "standard" ]]; then
    for kas in alpha beta; do
      local log_file=$(get_log_file "kas-${kas}")
      if [[ -f "${log_file}" ]]; then
        echo -e "  KAS ${kas}: ${BLUE}${log_file}${RESET}"
      else
        echo -e "  KAS ${kas}: ${YELLOW}${log_file}${RESET} (not yet created)"
      fi
    done
  elif [[ "${MODE}" == "full" ]]; then
    for kas in alpha beta gamma delta km1 km2; do
      local log_file=$(get_log_file "kas-${kas}")
      if [[ -f "${log_file}" ]]; then
        echo -e "  KAS ${kas}: ${BLUE}${log_file}${RESET}"
      else
        echo -e "  KAS ${kas}: ${YELLOW}${log_file}${RESET} (not yet created)"
      fi
    done
  fi
}

show_quick_commands() {
  echo ""
  echo -e "${BOLD}Quick Commands:${RESET}"
  echo "  Ctrl-b '     - Switch to window by name"
  echo "                 (e.g., type: docker, platform, tests)"
  echo "  Ctrl-b w     - Window list (interactive)"
  echo "  Ctrl-b n/p   - Next/previous window"
  echo "  Ctrl-b d     - Detach from session"
  echo "  Ctrl-b ?     - Show all keybindings"
}

show_test_commands() {
  echo ""
  echo -e "${BOLD}Run Tests:${RESET}"
  echo "  Switch to window 9 (Ctrl-b 9) and run:"
  echo "    pytest test_tdfs.py"
  echo "    pytest --focus go test_abac.py"
  echo "    pytest -v --html=report.html test_tdfs.py"
  echo "    ./run-local.sh test_tdfs.py"
}

show_service_commands() {
  echo ""
  echo -e "${BOLD}Service Management:${RESET}"
  echo "  Restart a service:"
  echo "    1. Switch to service window (Ctrl-b <number>)"
  echo "    2. Press Ctrl-c to stop"
  echo "    3. Press Up arrow and Enter to restart"
  echo ""
  echo "  View logs from another terminal:"
  echo "    tail -f ${LOG_DIR}/kas-main.log"
  echo "    tail -f ${LOG_DIR}/kas-alpha.log"
}

show_exit_commands() {
  echo ""
  echo -e "${BOLD}Exit:${RESET}"
  echo "  Detach:      Ctrl-b d  (keeps services running)"
  echo "  Stop all:    ./tmux-dev.sh --stop"
}

# Main display
clear
echo -e "${BOLD}=== OpenTDF Development Environment ===${RESET}"
echo "Mode: ${MODE}"
echo "Session: opentdf-dev"
echo "Updated: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

show_service_status
show_log_files
show_quick_commands
show_test_commands
show_service_commands
show_exit_commands

echo ""
echo -e "${YELLOW}This panel updates every 2 seconds${RESET}"
