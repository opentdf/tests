#!/usr/bin/env bash
set -euo pipefail

ETERNIA_PATH="../../../../eternia"
RUNNER_REPO="virtru/eternia-kuttl-runner"

[ -d $ETERNIA_PATH ] && echo "\nFound eternia repo" || printf "\nIn order to build this test runner, you need a copy of the Eternia git repo cloned next to your backend top-level folder"

pushd ../../../../eternia

printf "\nMoving to Eternia to build base image with SDK-CLI..\n"
RUNNER_VER=$(git rev-parse --short HEAD) # Use the current Eternia Git commit SHA as this test runner's image tag

printf '\nTagging this test runner with current Eternia HEAD: %s\n' "$RUNNER_VER"

docker build --target tester -t eternia-base . && popd

docker build -t $RUNNER_REPO:$RUNNER_VER .

printf "\nBuilt $RUNNER_REPO:$RUNNER_VER image - make sure to push this to Dockerhub so it can be used by cluster tests:\n"
printf "\ndocker push $RUNNER_REPO:$RUNNER_VER\n"
