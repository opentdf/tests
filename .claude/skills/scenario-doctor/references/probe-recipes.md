# Probe recipes

Shell snippets the `scenario-doctor` skill uses (or recommends users run by hand) to inspect running services and compare against `instance.yaml` expectations. `scripts/diff-running-vs-intended.sh` automates the common path; reach for these recipes when the script's output needs deeper investigation or the agent has to answer an ad-hoc "what's actually running on port X?" question.

## Identify what's listening on the conventional ports

```bash
lsof -nP -iTCP:8080,8181,8282,8383,8484,8585,8686,5432,8888 -sTCP:LISTEN
```

Reads as `COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME`. The PID is what to chase next.

## Resolve a PID to the binary path and its source worktree

```bash
ps -o command= -p <PID>
# → /Users/.../tests/xtest/platform/dist/<slug>/service start --config-file …
```

The binary lives at `…/dist/<slug>/service`. Its sibling `.version` file records the source worktree and git SHA that built it:

```bash
cat "$(dirname "$(ps -o command= -p <PID> | awk '{print $1}')")/.version"
# ref=refs/pull/3537/head
# sha=08ab3a0aef…
# worktree=/Users/.../DSPX-3302-02-platform-installer/tests/xtest/platform/src/refs--pull--3537--head
```

Whatever the `worktree=` line says is the directory the service binary loads keys / templates relative to — useful when investigating "platform started but says key X not found."

## Resolve a PID to its cwd (often a different worktree than the agent)

```bash
lsof -p <PID> -d cwd -Fn | awk '/^n/ { sub(/^n/,""); print; exit }'
```

A PID's cwd reveals which worktree initiated the service. Use this to spot cases where the agent thinks it's in worktree A but a sibling worktree B owns the running binary.

## Compare expected ref to actual ref for an instance

```bash
inst="tests/instances/<name>/instance.yaml"
yq -r '.platform.source.ref // .platform.dist' "$inst"       # expected
ps -o command= -p "$(lsof -nP -iTCP:8080 -sTCP:LISTEN | awk 'NR>1 {print $2; exit}')" \
  | awk '{print $1}' | xargs -I{} cat "$(dirname {})/.version"  # actual
```

Diff the two. Mismatch → either the instance is being served by a stale binary or by a binary from a different worktree.

## Health pings

```bash
curl -fsS http://localhost:8080/healthz   # platform
curl -fsS http://localhost:8585/healthz   # km1
```

Returns `{"status":"SERVING"}` (HTTP 200) when healthy. Anything else is a real failure — check the corresponding log under `tests/instances/<name>/logs/`.

## Confirm seed files exist (not Docker-created empty dirs)

```bash
worktree="…/xtest/platform/src/<slug>"
for f in kas-private.pem kas-cert.pem kas-ec-private.pem kas-ec-cert.pem \
         keys/ca.jks keys/localhost.crt keys/localhost.key opentdf.yaml; do
  if [[ -f "$worktree/$f" ]]; then
    printf 'ok\t%s\n' "$f"
  elif [[ -d "$worktree/$f" ]]; then
    printf 'empty-dir\t%s\n' "$f"  # Docker bind-mount left a stub directory
  else
    printf 'missing\t%s\n' "$f"
  fi
done
```

`empty-dir` is the silent-failure shape: Docker auto-created the path as a directory because the source file didn't exist when compose first ran. Removing the stub and re-bootstrapping (via `scripts/bootstrap-pr-worktree.sh` or `init-temp-keys.sh`) is the fix.

## Detect cross-worktree docker compose sharing

```bash
docker ps --format '{{.Names}}' | grep -E -- '-keycloak-|-opentdfdb-' \
  | sed -E 's/-(keycloak|opentdfdb)-[0-9]+$//' | sort -u
```

Lists every compose-project name currently sharing the docker daemon. Each project is typically named after the directory `docker compose` was invoked from (i.e. a worktree's `xtest/platform/src/<slug>/`). When multiple projects appear, `otdf-local --instance X down` will *not* stop docker — another instance is still using it.

## Kill a stale platform/KAS process (use with care)

```bash
pkill -9 -f "/dist/<slug>/service start"     # platform
pkill -9 -f "/dist/<slug>/service kas start" # KAS
```

Prefer `otdf-local --instance <name> down` when possible; `pkill` is the escape hatch when the instance owning the process doesn't match the worktree the agent is in (so `otdf-local` won't manage it cleanly).
