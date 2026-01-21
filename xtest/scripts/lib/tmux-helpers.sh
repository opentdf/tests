#!/usr/bin/env bash
# tmux session management utilities for local xtest execution

# Source common config if not already sourced
if [ -z "${TMUX_SESSION:-}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    source "$SCRIPT_DIR/common.sh"
fi

# Check if tmux session exists
session_exists() {
    tmux has-session -t "$TMUX_SESSION" 2>/dev/null
}

# Create new tmux session
create_session() {
    if session_exists; then
        log_warn "Session '$TMUX_SESSION' already exists"
        return 0
    fi

    log_info "Creating tmux session '$TMUX_SESSION'"
    tmux new-session -d -s "$TMUX_SESSION" -n "control"

    # Set up initial window with status display
    tmux send-keys -t "$TMUX_SESSION:control" "cd '$XTEST_DIR' && echo 'xtest control window - use Ctrl-b <number> to switch windows'" Enter
}

# Create a new window in the session
create_window() {
    local name="$1"
    local cmd="${2:-}"

    if ! session_exists; then
        log_error "Session '$TMUX_SESSION' does not exist"
        return 1
    fi

    # Check if window already exists
    if tmux list-windows -t "$TMUX_SESSION" -F "#{window_name}" | grep -q "^${name}$"; then
        log_warn "Window '$name' already exists in session"
        return 0
    fi

    log_info "Creating window '$name'"
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
        log_error "Session '$TMUX_SESSION' does not exist"
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
        log_info "Killing window '$window'"
        tmux kill-window -t "$TMUX_SESSION:$window"
    fi
}

# Kill entire session
kill_session() {
    if session_exists; then
        log_info "Killing tmux session '$TMUX_SESSION'"
        tmux kill-session -t "$TMUX_SESSION"
    fi
}

# Attach to session
attach_session() {
    if ! session_exists; then
        log_error "Session '$TMUX_SESSION' does not exist"
        return 1
    fi
    tmux attach-session -t "$TMUX_SESSION"
}

# List all windows
list_windows() {
    if ! session_exists; then
        log_error "Session '$TMUX_SESSION' does not exist"
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
        ((attempt++))
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
    cat <<EOF
tmux Session: $TMUX_SESSION

Window Layout:
  0: control    - Status/commands
  1: platform   - Main platform (port $PLATFORM_PORT)
  2: kas-alpha  - KAS (port ${KAS_CONFIG[alpha]})
  3: kas-beta   - KAS (port ${KAS_CONFIG[beta]})
  4: kas-gamma  - KAS (port ${KAS_CONFIG[gamma]})
  5: kas-delta  - KAS (port ${KAS_CONFIG[delta]})
  6: kas-km1    - KAS (port ${KAS_CONFIG[km1]}, key management)
  7: kas-km2    - KAS (port ${KAS_CONFIG[km2]}, key management)
  8: docker     - Docker logs
  9: tests      - pytest execution

Navigation:
  tmux attach -t $TMUX_SESSION    # Attach to session
  Ctrl-b <number>                  # Switch to window
  Ctrl-b d                         # Detach from session
  Ctrl-b [                         # Enter scroll mode (q to exit)
EOF
}
