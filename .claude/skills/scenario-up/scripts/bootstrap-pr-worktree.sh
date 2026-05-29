#!/usr/bin/env bash
# bootstrap-pr-worktree.sh — ensure platform source worktrees referenced by a
# scenario have the seed files otdf-local + docker-compose expect.
#
# Usage: bootstrap-pr-worktree.sh <path-to-scenario.yaml>
#
# A fresh `otdf-sdk-mgr install tip --ref <ref> platform` produces the
# /service binary and a populated git worktree at xtest/platform/src/<slug>/,
# but it does NOT generate the dev keys (kas-*.pem, keys/ca.jks, …) or copy
# opentdf-dev.yaml → opentdf.yaml. `otdf-local up` then fails in cryptic
# ways (Keycloak "Is a directory", platform "no such file"). This script
# pre-flights each referenced worktree and either bootstraps or fails loudly
# with the exact remedy.
#
# Output: tab-separated, header on first line.
# Columns: worktree  file  state  action
#   state ∈ { ok | missing | empty-dir }
#   action ∈ { kept | generated | copied | manual-required }

set -u

if [[ $# -lt 1 ]]; then
  echo "usage: $(basename "$0") <scenario.yaml>" >&2
  exit 2
fi

scenario="$1"
[[ -f "$scenario" ]] || { echo "scenario not found: $scenario" >&2; exit 2; }

# Resolve repo root (the dir containing xtest/) by walking up from $scenario.
dir="$(cd "$(dirname "$scenario")" && pwd)"
while [[ "$dir" != "/" && ! -d "$dir/xtest" ]]; do dir="$(dirname "$dir")"; done
[[ -d "$dir/xtest" ]] || { echo "could not locate xtest/ above $scenario" >&2; exit 2; }
PLATFORM_DIST="$dir/xtest/platform/dist"

# Files each worktree needs. Order matters for the action log — opentdf.yaml
# last so its "copied from opentdf-dev.yaml" message lands after the keys.
REQUIRED_FILES=(
  kas-private.pem
  kas-cert.pem
  kas-ec-private.pem
  kas-ec-cert.pem
  keys/ca.jks
  keys/localhost.crt
  keys/localhost.key
  opentdf.yaml
)

# Extract referenced refs from the scenario. We tolerate yq presence/absence:
# prefer `yq -r` when available, fall back to a grep that handles the two
# shapes we emit (`ref: pr:3537` inline and `{ ref: pr:3537 }` flow-style).
refs=()
if command -v yq >/dev/null 2>&1; then
  while IFS= read -r r; do [[ -n "$r" && "$r" != "null" ]] && refs+=("$r"); done < <(
    yq -r '
      [ .instance.platform.source.ref?,
        (.instance.kas[]?.source.ref?)
      ] | .[] | select(. != null)
    ' "$scenario" 2>/dev/null | sort -u
  )
else
  while IFS= read -r r; do refs+=("$r"); done < <(
    grep -E '\{?\s*ref:' "$scenario" | sed -E 's/.*ref:[[:space:]]*"?([^",}[:space:]]+)"?.*/\1/' | sort -u
  )
fi

if [[ ${#refs[@]} -eq 0 ]]; then
  echo "no source.ref pins found in $scenario (dist-only scenario, nothing to bootstrap)" >&2
  exit 0
fi

printf 'worktree\tfile\tstate\taction\n'

for ref in "${refs[@]}"; do
  # Slug used by otdf-sdk-mgr: replace `/` and `:` with `--`. Mutable refs
  # like `main`, `pr:3537` get slugs `main`, `refs--pull--3537--head` (the
  # `pr:N` shorthand expands inside the installer). Read the .version sidecar
  # to get the canonical worktree path rather than guess.
  dist_dir=""
  for slug_candidate in "$PLATFORM_DIST"/*/; do
    [[ -f "$slug_candidate/.version" ]] || continue
    if grep -Fq "ref=$ref" "$slug_candidate/.version" || grep -Fq "ref=refs/pull/${ref#pr:}/head" "$slug_candidate/.version"; then
      dist_dir="${slug_candidate%/}"; break
    fi
  done
  if [[ -z "$dist_dir" ]]; then
    printf '%s\t-\tmissing\tmanual-required\n' "$ref"
    echo "no dist dir found for ref=$ref; run 'otdf-sdk-mgr install tip --ref $ref platform' first" >&2
    continue
  fi
  worktree="$(awk -F= '/^worktree=/ {print $2}' "$dist_dir/.version")"
  [[ -d "$worktree" ]] || { printf '%s\t.version\tmissing\tmanual-required\n' "$ref"; continue; }

  for f in "${REQUIRED_FILES[@]}"; do
    path="$worktree/$f"
    if [[ -f "$path" ]]; then
      printf '%s\t%s\tok\tkept\n' "$worktree" "$f"
      continue
    fi
    if [[ -d "$path" ]]; then
      # Docker bind-mount created an empty dir on a prior failed up. Remove it
      # so the bootstrap fill below can replace it with a real file.
      rmdir "$path" 2>/dev/null || true
      printf '%s\t%s\tempty-dir\tremoved\n' "$worktree" "$f"
    fi

    # Fill rules:
    #   opentdf.yaml: cp opentdf-dev.yaml → opentdf.yaml (legacy template name).
    #   everything else: try copying from xtest/platform/src/main/, else fail.
    if [[ "$f" == "opentdf.yaml" && -f "$worktree/opentdf-dev.yaml" ]]; then
      cp "$worktree/opentdf-dev.yaml" "$path"
      printf '%s\t%s\tmissing\tcopied(opentdf-dev.yaml)\n' "$worktree" "$f"
      continue
    fi

    main_dir="$dir/xtest/platform/src/main"
    if [[ -f "$main_dir/$f" ]]; then
      mkdir -p "$(dirname "$path")"
      cp "$main_dir/$f" "$path"
      printf '%s\t%s\tmissing\tcopied(main)\n' "$worktree" "$f"
      continue
    fi

    printf '%s\t%s\tmissing\tmanual-required\n' "$worktree" "$f"
    cat >&2 <<EOF
missing: $path
  remedy: cd "$worktree" && bash .github/scripts/init-temp-keys.sh
          (run from inside the worktree; generates kas-*.pem and keys/*)
EOF
  done
done
