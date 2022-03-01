#!/bin/bash
# Alias for `git clone` with support for narrow clones, assumes opentdf org
#
#   Usage: clonk [repo name] [branch or tag or commit id] (path)
#
# Advantages:
#
# * Assumes your repo is in github/opentdf/[repo name]
# * If you've already checked it out, just update it
# * Clones and checks out a specfic branch all at once, if you want
# * Allows narrow sparse clones with the third [path] option.

_clonk() {
  local name="$1"
  local repo="git@github.com:opentdf/${name}.git"
  shift

  local branch=${1:-main}
  shift

  local subdir=("${@}")

  echo --- "Clonkeding ${repo} ${branch} ${subdir[@]}"

  if [ -d "${name}" ]; then
    (
      cd "${name}" || exit 1
      if ! git fetch; then
        echo "Failed to fetch ${repo}"
        exit 1
      fi
      if ! git checkout "${branch}"; then
        echo "Failed to check out ${repo} ${branch}"
        exit 1
      fi
      if [[ $subdir ]] && git help sparse-checkout >/dev/null; then
        if ! git sparse-checkout set "${subdir[@]}"; then
          echo "Failed to configure checkout ${subdir[@]} from ${repo}"
          exit 1
        fi
        if ! git checkout; then
          echo "Failed to narrow checkout ${repo}"
          exit 1
        fi
      fi
    )
  elif [[ $subdir ]] && git help sparse-checkout >/dev/null; then
    if ! git clone --filter=blob:none --no-checkout -b "$branch" "$repo"; then
      echo "Failed to sparse clone ${repo}"P
      exit 1
    fi
    (
      cd "${name}" || exit 1
      if ! git sparse-checkout init --cone; then
        echo "Failed to initialize sparse clone of $repo"
        exit 1
      fi
      if ! git sparse-checkout set "${subdir[@]}"; then
        echo "Failed to configure checkout ${subdir[@]} from ${repo}"
        exit 1
      fi
      if ! git checkout; then
        echo "Failed to narrow checkout ${repo}"
        exit 1
      fi
    )
  else
    echo "Non-sparse mode checkout, git version == [$(git version)]"
    if ! git clone -b "$branch" "$repo"; then
      echo "Failed to dense clone $repo"
      exit 1
    fi
  fi
  (
    cd "${name}" || exit 1
    echo "Checked out ${repo} at $(git rev-parse HEAD)"
  )
}

_clonk "$@"
