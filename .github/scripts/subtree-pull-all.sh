#!/usr/bin/env bash

projects=( backend client-web frontend tdf3-js )
now=$(date +"%Y-%m-%dT%H:%M:%S%z")

for project in "${projects[@]}"; do
  m="🔀 git subtree pull $project at $now"
  if ! git subtree pull -m "$m" -P "$project" "git@github.com:/opentdf/$project" main; then
    echo "Unable to pull $project"
    exit 1
  fi
done

if ! git log -1 | grep "at $now"; then
  echo "No changes found"
fi

