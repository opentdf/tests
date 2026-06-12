#!/usr/bin/env bash
# check-instance-seed.sh — read-only verifier that `otdf-local instance init`
# left the instance dir with the seed bundle `up` and pytest expect.
#
# Usage: check-instance-seed.sh <instance-name>
#
# `instance init` self-provisions: keys/{ca.jks,localhost.crt,localhost.key},
# keys/kas-{private,cert,ec-private,ec-cert}.pem, and instances/<name>/opentdf.yaml
# with a generated services.kas.root_key. This script confirms each is present
# and reports tab-separated rows; it does not modify anything.
#
# Output: tab-separated, header on first line.
# Columns: artifact  state  detail
#   state ∈ { ok | missing | empty }

set -u

if [[ $# -lt 1 ]]; then
  echo "usage: $(basename "$0") <instance-name>" >&2
  exit 2
fi

name="$1"

# Resolve repo root by walking up from $PWD until we find the tests/ marker.
dir="$PWD"
while [[ "$dir" != "/" && ! -d "$dir/instances" ]]; do dir="$(dirname "$dir")"; done
if [[ ! -d "$dir/instances" ]]; then
  echo "could not locate tests/instances/ above $PWD" >&2
  exit 2
fi
instance_dir="$dir/instances/$name"
if [[ ! -d "$instance_dir" ]]; then
  echo "instance not found: $instance_dir" >&2
  exit 2
fi

REQUIRED_FILES=(
  keys/ca.jks
  keys/localhost.crt
  keys/localhost.key
  keys/kas-private.pem
  keys/kas-cert.pem
  keys/kas-ec-private.pem
  keys/kas-ec-cert.pem
  opentdf.yaml
)

printf 'artifact\tstate\tdetail\n'

for f in "${REQUIRED_FILES[@]}"; do
  path="$instance_dir/$f"
  if [[ ! -e "$path" ]]; then
    printf '%s\tmissing\t-\n' "$f"
  elif [[ -d "$path" ]]; then
    printf '%s\tempty\tdirectory leftover (docker bind-mount stub)\n' "$f"
  elif [[ ! -s "$path" ]]; then
    printf '%s\tempty\tzero bytes\n' "$f"
  else
    printf '%s\tok\t-\n' "$f"
  fi
done

# Confirm the per-instance root_key got written into opentdf.yaml.
config="$instance_dir/opentdf.yaml"
if [[ -f "$config" ]]; then
  if command -v yq >/dev/null 2>&1; then
    rk="$(yq -r '.services.kas.root_key // ""' "$config" 2>/dev/null)"
  else
    rk="$(grep -E '^[[:space:]]*root_key:' "$config" 2>/dev/null | head -1 | sed -E 's/.*root_key:[[:space:]]*"?([^"[:space:]]+)"?.*/\1/')"
  fi
  if [[ -z "$rk" || "$rk" == "null" ]]; then
    printf '%s\tmissing\troot_key empty in opentdf.yaml\n' "services.kas.root_key"
  else
    printf '%s\tok\t-\n' "services.kas.root_key"
  fi
fi
