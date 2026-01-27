#!/usr/bin/env bash
# tmux session management utilities for local xtest execution
# CRITICAL: NO shell options (set -e, set -o pipefail) - consumer scripts control error handling

# Determine library directory (bash/zsh compatible)
if [ -n "${BASH_SOURCE:-}" ]; then
  _TMUX_FILE="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
  _TMUX_FILE="${(%):-%x}"
else
  _TMUX_FILE="$0"
fi
_TMUX_DIR="$(cd "$(dirname "$_TMUX_FILE")" && pwd)"

# Source logging if available
if [ -f "$_TMUX_DIR/../core/logging.sh" ]; then
  # shellcheck source=../core/logging.sh
  source "$_TMUX_DIR/../core/logging.sh"
fi

# Default session name (can be overridden by setting TMUX_SESSION before sourcing)
: "${TMUX_SESSION:=xtest}"

# Check if tmux session exists
session_exists() {
  if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    return 0
  else
    return 1
  fi
}

# Create new tmux session
create_session() {
  if session_exists; then
    if type log_warn >/dev/null 2>&1; then
      log_warn "Session '$TMUX_SESSION' already exists"
    fi
    return 0
  fi

  if type log_info >/dev/null 2>&1; then
    log_info "Creating tmux session '$TMUX_SESSION'"
  fi

  tmux new-session -d -s "$TMUX_SESSION" -n "control"

  # Set up initial window with status display
  local xtest_dir="${XTEST_DIR:-$(cd "$_TMUX_DIR/../../.." && pwd)}"
  tmux send-keys -t "$TMUX_SESSION:control" "cd '$xtest_dir' && echo 'xtest control window - use Ctrl-b <number> to switch windows'" Enter
}

# Create a new window in the session
create_window() {
  local name="$1"
  local cmd="${2:-}"

  if ! session_exists; then
    if type log_error >/dev/null 2>&1; then
      log_error "Session '$TMUX_SESSION' does not exist"
    fi
    return 1
  fi

  # Check if window already exists
  if tmux list-windows -t "$TMUX_SESSION" -F "#{window_name}" | grep -q "^${name}$"; then
    if type log_warn >/dev/null 2>&1; then
      log_warn "Window '$name' already exists in session"
    fi
    return 0
  fi

  if type log_info >/dev/null 2>&1; then
    log_info "Creating window '$name'"
  fi
  tmux new-window -t "$TMUX_SESSION" -n "$name"

  if [ -n "$cmd" ]; then
    tmux send-keys -t "$TMUX_SESSION:$name" "$cmd" Enter
  fi
}

# Run command in a window
run_in_window() {
  local window="$1"
  shift
  local cmd="$*"

  if ! session_exists; then
    if type log_error >/dev/null 2>&1; then
      log_error "Session '$TMUX_SESSION' does not exist"
    fi
    return 1
  fi

  tmux send-keys -t "$TMUX_SESSION:$window" "$cmd" Enter
}

# Send interrupt (Ctrl-C) to a window
interrupt_window() {
  local window="$1"

  if ! session_exists; then
    return 0
  fi

  if tmux list-windows -t "$TMUX_SESSION" -F "#{window_name}" | grep -q "^${window}$"; then
    tmux send-keys -t "$TMUX_SESSION:$window" C-c
  fi
}

# Kill a specific window
kill_window() {
  local window="$1"

  if ! session_exists; then
    return 0
  fi

  if tmux list-windows -t "$TMUX_SESSION" -F "#{window_name}" | grep -q "^${window}$"; then
    if type log_info >/dev/null 2>&1; then
      log_info "Killing window '$window'"
    fi
    tmux kill-window -t "$TMUX_SESSION:$window"
  fi
}

# Kill entire session
kill_session() {
  if session_exists; then
    if type log_info >/dev/null 2>&1; then
      log_info "Killing tmux session '$TMUX_SESSION'"
    fi
    tmux kill-session -t "$TMUX_SESSION"
  fi
}

# Attach to session
attach_session() {
  if ! session_exists; then
    if type log_error >/dev/null 2>&1; then
      log_error "Session '$TMUX_SESSION' does not exist"
    fi
    return 1
  fi
  tmux attach-session -t "$TMUX_SESSION"
}

# List all windows
list_windows() {
  if ! session_exists; then
    if type log_error >/dev/null 2>&1; then
      log_error "Session '$TMUX_SESSION' does not exist"
    fi
    return 1
  fi
  tmux list-windows -t "$TMUX_SESSION" -F "#{window_index}: #{window_name}"
}

# Get window pane content (last N lines)
get_window_output() {
  local window="$1"
  local lines="${2:-50}"

  if ! session_exists; then
    return 1
  fi

  tmux capture-pane -t "$TMUX_SESSION:$window" -p -S "-$lines"
}

# Wait for specific text in window output
wait_for_window_text() {
  local window="$1"
  local text="$2"
  local max_attempts="${3:-60}"
  local attempt=1

  while [ "$attempt" -le "$max_attempts" ]; do
    if get_window_output "$window" 100 | grep -q "$text"; then
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done
  return 1
}

# Create all windows for xtest session layout
create_all_windows() {
  # Window 0: control (created with session)
  # Window 1: platform
  create_window "platform"
  # Windows 2-7: KAS instances (in alphabetical order)
  create_window "kas-alpha"
  create_window "kas-beta"
  create_window "kas-gamma"
  create_window "kas-delta"
  create_window "kas-km1"
  create_window "kas-km2"
  # Window 8: docker logs
  create_window "docker"
  # Window 9: tests
  create_window "tests"
}

# Show session layout help
show_layout_help() {
  # Try to get KAS_CONFIG if available
  local alpha_port="${KAS_CONFIG[alpha]:-8181}"
  local beta_port="${KAS_CONFIG[beta]:-8282}"
  local gamma_port="${KAS_CONFIG[gamma]:-8383}"
  local delta_port="${KAS_CONFIG[delta]:-8484}"
  local km1_port="${KAS_CONFIG[km1]:-8585}"
  local km2_port="${KAS_CONFIG[km2]:-8686}"
  local platform_port="${PLATFORM_PORT:-8080}"

  cat <<EOF
tmux Session: $TMUX_SESSION

Window Layout:
  0: control    - Status/commands
  1: platform   - Main platform (port $platform_port)
  2: kas-alpha  - KAS (port $alpha_port)
  3: kas-beta   - KAS (port $beta_port)
  4: kas-gamma  - KAS (port $gamma_port)
  5: kas-delta  - KAS (port $delta_port)
  6: kas-km1    - KAS (port $km1_port, key management)
  7: kas-km2    - KAS (port $km2_port, key management)
  8: docker     - Docker logs
  9: tests      - pytest execution

Navigation:
  tmux attach -t $TMUX_SESSION    # Attach to session
  Ctrl-b <number>                  # Switch to window
  Ctrl-b d                         # Detach from session
  Ctrl-b [                         # Enter scroll mode (q to exit)
EOF
}
