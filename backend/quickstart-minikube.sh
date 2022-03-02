#!/usr/bin/env bash
set -euo pipefail

make local-cluster

printf "\nAll Done! Fire up 'octant' or similar to have a look at the cluster\n"
