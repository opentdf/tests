#!/usr/bin/env bash
# Bash functions for kind

local_load() {
  kind load docker-image "${@}"
}

local_info() {
  kind version
}

local_start() {
  kind create cluster
}

local_clean() {
  kind delete cluster
}
