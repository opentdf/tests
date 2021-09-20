#!/usr/bin/env bash
# Generate `tdf3-export.zip` containing:
#   * tdf3-services.zip: a zip file of this project's main branch
#   * docker images of kas and eas
#   * Javascript and Python library binary-ish things from npm and pypi

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd)"
PROJECT_ROOT="$(cd "$APP_DIR"/../ >/dev/null && pwd)"
export PATH="$PATH:$APP_DIR"

if ! cd "$PROJECT_ROOT"; then
  monolog ERROR "Unable to find project root [${PROJECT_ROOT}] from APP_DIR=[${APP_DIR}]"
  exit 1
fi

mkdir -p build/export

# EXPORT SERVICES SOURCE AS ZIP FILE
if ! git archive --format zip --output build/export/tdf3-services.zip master; then
  monolog ERROR "Failed to create etheria archive, tdf3-service.zip"
  exit 1
fi

# BUILD KAS AND AS DOCKER IMAGES
EAS_VERSION=$(<eas/VERSION)
KAS_VERSION=$(<kas_app/VERSION)
ABACUS_VERSION=$(grep version abacus/web/package.json | awk -F \" '{print $4}')

export EAS_VERSION
export KAS_VERSION
export ABACUS_VERSION

if ! docker-compose -f docker-compose.yml up --build -d; then
  monolog ERROR "Failed to create docker images"
  exit 1
fi

if ! docker save -o build/export/docker-images.tar tdf3.service.eas:"${EAS_VERSION}" tdf3.service.kas:"${KAS_VERSION}" tdf3.service.abacus:"${ABACUS_VERSION}" nginx:1.19.4 python:3; then
  monolog ERROR "Failed to save docker images"
  exit 1
fi

maybe-exit() {
  local err="$?"
  if [[ ! $err ]]; then
    monolog ERROR "$1; err=$err"
    exit 1
  fi
}

# DOWNLOAD SOME SDKS
TDF3_LATEST=$(curl -s http://registry.npmjs.org/tdf3-js/latest/ | sed 's/.*"tarball":"\([^"]*\).*/\1/')
TDF3_TGZ=$(echo "$TDF3_LATEST" | sed 's/.*-\/\(.*\.tgz\)$/\1/')
curl -s "https://registry.npmjs.org/tdf3-js/-/$TDF3_TGZ" --output "build/export/sdk-$TDF3_TGZ"
maybe-exit "Failed to get latest of tdf3-js (${TDF3_LATEST}) from NPM, expected at [${TDF3_TGZ}]"

NANOTDF_LATEST=$(curl -s http://registry.npmjs.org/nanotdf-sdk/latest/ | sed 's/.*"tarball":"\([^"]*\).*/\1/')
NANOTDF_TGZ=$(echo "$NANOTDF_LATEST" | sed 's/.*-\/\(.*\.tgz\)$/\1/')
curl -s "https://registry.npmjs.org/nanotdf-sdk/-/$NANOTDF_TGZ" --output "build/export/$NANOTDF_TGZ"
maybe-exit "Failed to get latest of nanotdf-sdk (${NANOTDF_LATEST}) from NPM, expected at [${NANOTDF_TGZ}]"

VIRTRU_LATEST=$(curl -s http://registry.npmjs.org/virtru-sdk/latest/ | sed 's/.*"tarball":"\([^"]*\).*/\1/')
VIRTRU_TGZ=$(echo "$VIRTRU_LATEST" | sed 's/.*-\/\(.*\.tgz\)$/\1/')
curl -s "https://registry.npmjs.org/virtru-sdk/-/$VIRTRU_TGZ" --output "build/export/$VIRTRU_TGZ"
maybe-exit "Failed to get latest of virtru-sdk (${VIRTRU_LATEST}) from NPM, expected at [${VIRTRU_TGZ}]"

pip-latest() {
  local project
  project="$1"
  shift

  local deets
  deets="$(curl -s "https://pypi.org/pypi/${project}/json")"
  maybe-exit "Getting details of [${project}] failed with $?"

  local version
  version="$(jq -r '.info.version' <<<"${deets}")"
  maybe-exit "Getting latest version of [${project}] failed"

  local variants
  variants=$(jq -r --arg version "$version" '.releases[$version]' <<<"${deets}")
  maybe-exit "Getting latest version of [${project}] failed"

  local len
  len=$(jq -r 'length' <<<"$variants")
  maybe-exit "Surprising variants object"
  [[ $len ]]
  maybe-exit "len=[$len]"
  monolog INFO "Found $len variants of $project $version"

  local filename
  local url
  for ((i = 0; i < len; i++)); do
    filename=$(jq -r --argjson i "$i" '.[$i].filename' <<<"${variants}")
    url=$(jq -r --argjson i "$i" '.[$i].url' <<<"${variants}")
    [[ $filename && $url ]]
    maybe-exit "filename=[$filename] url=[$url]"
    monolog INFO "Downloading $filename from $url"
    curl -s "${url}" >"build/export/${filename}"
    maybe-exit "Failed downloading [$url]"
  done
}

pip-latest tdf3sdk
pip-latest virtru-sdk

# BUNDLE THAT STUFF UP
fname="export-$(date +%Y-%m-%d).zip"
if ! cd build && zip -r "${fname}" export; then
  monolog ERROR "Failed to export as zip file"
  exit 1
fi

monolog DEBUG "Saved stuff as build/${fname}"
