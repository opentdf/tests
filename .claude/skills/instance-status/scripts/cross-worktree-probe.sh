#!/usr/bin/env bash
# cross-worktree-probe.sh — surface listeners on opentdf test ports across ALL worktrees.
#
# `otdf-local instance ls` is scoped to one worktree's tests/instances/; sibling
# worktrees' running services are invisible to it. This script probes the host
# directly so the agent can detect cross-worktree port collisions before
# `scenario-up` (or explain why a port appears "free" from one CLI but isn't).
#
# Output: tab-separated, one record per line, header on first line.
# Columns: port  proto  pid  cwd  kind
#   kind ∈ { platform | kas | docker-keycloak | docker-postgres | unknown }

set -u

PORTS=(8080 8181 8282 8383 8484 8585 8686 5432 8888)

printf 'port\tproto\tpid\tcwd\tkind\n'

for port in "${PORTS[@]}"; do
  # -F to use parseable format; -n -P to skip name resolution (faster)
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    pid="$(awk '{print $2}' <<<"$line")"
    [[ -z "$pid" || "$pid" == "PID" ]] && continue

    cwd="$(lsof -p "$pid" -d cwd -Fn 2>/dev/null | awk '/^n/ { sub(/^n/,""); print; exit }')"
    cwd="${cwd:-?}"

    cmd="$(ps -o command= -p "$pid" 2>/dev/null | head -c 200)"
    case "$port" in
      8080) kind=platform ;;
      8181|8282|8383|8484|8585|8686) kind=kas ;;
      8888) kind=docker-keycloak ;;
      5432) kind=docker-postgres ;;
      *)    kind=unknown ;;
    esac
    # Refine kind if process command says otherwise (e.g. a misbound port).
    case "$cmd" in
      *"/service "*) kind=platform ;;
      *opentdf-kas*|*"kas start"*) kind=kas ;;
    esac

    printf '%s\ttcp\t%s\t%s\t%s\n' "$port" "$pid" "$cwd" "$kind"
  done < <(lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | tail -n +2)
done

# Docker compose projects sharing the host docker daemon — names like
# `<project>-keycloak-1`, `<project>-opentdfdb-1`. The project is whatever
# directory `docker compose` was invoked from (typically a worktree's
# xtest/platform/src/<ref>/ directory).
docker ps --format '{{.Names}}' 2>/dev/null | while IFS= read -r name; do
  [[ -z "$name" ]] && continue
  case "$name" in
    *-keycloak-*)  printf 'compose\tdocker\t-\t%s\tcompose-project\n' "${name%-keycloak-*}" ;;
    *-opentdfdb-*) printf 'compose\tdocker\t-\t%s\tcompose-project\n' "${name%-opentdfdb-*}" ;;
  esac
done | sort -u
