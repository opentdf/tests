#!/usr/bin/env bash
# diff-running-vs-intended.sh — verify that running services match what an
# instance.yaml claims they should be.
#
# Usage: diff-running-vs-intended.sh <instance-name>
#
# Walks the per-instance manifest at tests/instances/<name>/instance.yaml,
# resolves each pin (dist:/source.ref:) to its expected dist directory and
# git SHA via the .version sidecar, then compares against what's actually
# listening on the conventional ports.
#
# Output: tab-separated, header on first line.
# Columns: service  port  expected_sha  actual_sha  health  status
#   status ∈ { MATCH | WRONG-BINARY | NOT-RUNNING | EXTRA | NO-PIN }
#   health ∈ { 200 | <http-code> | down | - }

set -u

if [[ $# -lt 1 ]]; then
  echo "usage: $(basename "$0") <instance-name>" >&2
  exit 2
fi

name="$1"

# Resolve repo root by walking up from CWD until we find tests/instances/.
dir="$PWD"
while [[ "$dir" != "/" && ! -d "$dir/tests/instances" && ! -d "$dir/instances" ]]; do
  dir="$(dirname "$dir")"
done
[[ -d "$dir/tests/instances" ]] && INST_ROOT="$dir/tests/instances"
[[ -d "$dir/instances" ]] && INST_ROOT="$dir/instances"
: "${INST_ROOT:?could not locate tests/instances/ above $PWD}"

inst="$INST_ROOT/$name/instance.yaml"
[[ -f "$inst" ]] || {
  echo "no instance.yaml at $inst" >&2
  exit 2
}

INST_DIR_PARENT="${INST_ROOT%/instances}"
PLATFORM_DIST="$INST_DIR_PARENT/xtest/platform/dist"

# Port map (matches otdf-local's Ports defaults).
declare -A PORT_OF=(
    [platform]=8080
    [alpha]=8181
    [beta]=8282
    [gamma]=8383
    [delta]=8484
    [km1]=8585
    [km2]=8686
)

# Helper: resolve a pin (ref or dist) to expected_sha by reading .version.
expected_sha_for() {
  local pin="$1" # could be a ref like 'main' or 'pr:3537', or a dist slug
  for cand in "$PLATFORM_DIST"/*/; do
    [[ -f "$cand/.version" ]] || continue
    if grep -Fq "ref=$pin" "$cand/.version" ||
      grep -Fq "ref=refs/pull/${pin#pr:}/head" "$cand/.version" ||
      [[ "$(basename "${cand%/}")" == "$pin" ]]; then
      awk -F= '/^sha=/ {print substr($2,1,12); exit}' "$cand/.version"
      return
    fi
  done
  echo "?"
}

# Helper: actual_sha by inspecting the running binary at $port.
actual_sha_for_port() {
  local port="$1"
  local pid binary version
  pid="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {print $2; exit}')"
  [[ -z "$pid" ]] && {
    echo ""
    return
  }
  binary="$(ps -o command= -p "$pid" 2>/dev/null | awk '{print $1}')"
  [[ -f "$binary" ]] || {
    echo "?"
    return
  }
  version="$(dirname "$binary")/.version"
  [[ -f "$version" ]] && awk -F= '/^sha=/ {print substr($2,1,12); exit}' "$version" || echo "?"
}

# Helper: http health code.
health_of() {
  local port="$1"
  curl -fsS -o /dev/null -w '%{http_code}' "http://localhost:$port/healthz" 2>/dev/null || echo down
}

# Extract pins from instance.yaml. yq optional; fall back to grep.
get_pin() {
  local field="$1" # e.g. .platform OR .kas.km1
  if command -v yq >/dev/null 2>&1; then
    yq -r "($field.source.ref? // $field.dist? // \"\")" "$inst"
  else
    # Crude fallback: pull the first ref|dist under the section name.
    awk -v sec="${field#.}" '
      $0 ~ "^"sec":" {f=1; next}
      f && /^[^[:space:]]/ {f=0}
      f && /(ref|dist):/ {gsub(/[",{}]/,""); for(i=1;i<=NF;i++) if($i ~ /^(ref|dist):/) {print $(i+1); exit}}
    ' "$inst"
  fi
}

printf 'service\tport\texpected_sha\tactual_sha\thealth\tstatus\n'

# Check if platform is configured for source mode (pre-PR#510 instances).
platform_uses_source=0
if command -v yq >/dev/null 2>&1; then
  [[ -n "$(yq -r '.platform.source.ref // ""' "$inst")" ]] && platform_uses_source=1
else
  grep -q 'source:' "$inst" && platform_uses_source=1
fi
if [[ "$platform_uses_source" == 1 ]]; then
  echo "⚠️  WARNING: instance uses platform.source; binary builds are ignored" >&2
  echo "    Run: otdf-sdk-mgr install scenario $inst" >&2
  echo "    This will update instance.yaml to use platform.dist" >&2
fi

# Platform first.
pin="$(get_pin .platform)"
exp="$(expected_sha_for "$pin")"
act="$(actual_sha_for_port 8080)"
hc="$(health_of 8080)"
if [[ -z "$pin" ]]; then
  status=NO-PIN
elif [[ -z "$act" ]]; then
  status=NOT-RUNNING
elif [[ "$act" == "$exp" ]]; then
  status=MATCH
else status=WRONG-BINARY; fi
printf 'platform\t8080\t%s\t%s\t%s\t%s\n' "${exp:-?}" "${act:--}" "$hc" "$status"

# KAS instances declared in the manifest. Build the list either via yq or
# the grep fallback.
kas_names=()
if command -v yq >/dev/null 2>&1; then
  while IFS= read -r n; do kas_names+=("$n"); done < <(yq -r '.kas | keys[]' "$inst")
else
  while IFS= read -r n; do kas_names+=("$n"); done < <(
    awk '/^kas:/{f=1;next} f && /^[a-z0-9_-]+:/{gsub(":",""); print $1} f && /^[^[:space:]]/{f=0}' "$inst"
  )
fi

for kas in "${kas_names[@]}"; do
  port="${PORT_OF[$kas]:-?}"
  pin="$(get_pin ".kas.$kas")"
  exp="$(expected_sha_for "$pin")"
  act="$(actual_sha_for_port "$port")"
  hc="$([[ "$port" != "?" ]] && health_of "$port" || echo -)"
  if [[ -z "$pin" ]]; then
    status=NO-PIN
  elif [[ -z "$act" ]]; then
    status=NOT-RUNNING
  elif [[ "$act" == "$exp" ]]; then
    status=MATCH
  else status=WRONG-BINARY; fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$kas" "$port" "${exp:-?}" "${act:--}" "$hc" "$status"
done

# Detect EXTRA services: any port in PORT_OF that's listening but wasn't
# declared in instance.yaml.
declared_ports=(8080)
for k in "${kas_names[@]}"; do declared_ports+=("${PORT_OF[$k]:-0}"); done
for svc in "${!PORT_OF[@]}"; do
  port="${PORT_OF[$svc]}"
  in_declared=0
  for d in "${declared_ports[@]}"; do [[ "$d" == "$port" ]] && in_declared=1 && break; done
  [[ "$in_declared" == 1 ]] && continue
  act="$(actual_sha_for_port "$port")"
  [[ -z "$act" ]] && continue
  hc="$(health_of "$port")"
  printf '%s\t%s\t-\t%s\t%s\tEXTRA\n' "$svc" "$port" "$act" "$hc"
done
