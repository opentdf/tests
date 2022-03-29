#!/usr/bin/env bash
# Updates charts' `appVersion` fields to VERSION information found in
# corresponding containers.

chart-for() {
  echo "charts/$1/Chart.yaml"
}

version-for() {
  case "$1" in
    kas)
      echo "$(<containers/kas/kas_app/VERSION)"
      ;;
    keycloak_bootstrap)
      echo "$(<containers/keycloak-bootstrap/VERSION)"
      ;;
    *)
      echo "$(<containers/"$1"/VERSION)"
      ;;
  esac
}

set-appVersion() {
  APP_VERSION="$(version-for "$1")" yq -i '.appVersion = strenv(APP_VERSION)' "$(chart-for "$1")"
}

for x in $(cd charts && ls); do
  set-appVersion "$x"
done
