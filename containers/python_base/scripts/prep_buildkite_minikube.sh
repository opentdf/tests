#!/usr/bin/env bash

# Ditch this when we abandon Buildkite - all it does it stand up a minikube env
# with necessary local tooling on a build agent

TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd)"

# shellcheck disable=SC1091
LOCAL_TOOL=minikube . "${TOOLS_DIR}/prep_buildkite.sh" "${@}"
