#!/usr/bin/env bash
# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <uid> <tier> <encrypt | decrypt> <src-file> <dst-file>

JAVA_CLI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd)"
JAVA_JAR_DIR="$(cd "${JAVA_CLI_DIR}/../" >/dev/null && pwd)"
PROJECT_ROOT="$(cd "${JAVA_CLI_DIR}/../../../../" >/dev/null && pwd)"
export PATH="$PATH:$PROJECT_ROOT/scripts"

# PULL DOWN NECESSARY JARS
if ! compgen -G "${JAVA_JAR_DIR}/*.jar" >/dev/null; then
  monolog DEBUG "Retrieving dependency jar"
  curl -H "Accept: application/zip" https://repo1.maven.org/maven2/com/googlecode/json-simple/json-simple/1.1.1/json-simple-1.1.1.jar -o "${JAVA_JAR_DIR}"/json-simple-1.1.1.jar

  # PULL DOWN FROM BUILDKITE using local BK token
  # monolog INFO "Retrieving jar from BK"
  # URL=$(curl -H "Authorization: Bearer $BUILDKITE_API_TOKEN" "https://api.buildkite.com/v2/organizations/virtru/pipelines/tdf3-cpp/builds/1211/jobs/6a9d011a-6b7c-4efa-998b-0653cc7fb1af/artifacts/fba27550-554f-4ff3-9940-c188d250407c/download" | \
  #     python3 -c "import sys, json; print(json.load(sys.stdin)['url'])")
  # curl -H "Accept: application/zip" $URL -o tdf3-sdk.tar.gz
  # tar -xf tdf3-sdk.tar.gz
  # rm -rf tdf3-sdk.tar.gz
  # mv tdf3-lib-java/*.jar $(dirname "${BASH_SOURCE[0]}")/../
  # rm -rf tdf3-lib-java

  # Extract jar when artifact pulled with BK agent -- test-in-containers
  monolog DEBUG "Extracting jar from artifact"
  if [ -e "${JAVA_JAR_DIR}/${JAVA_BUILD_ARTIFACT}" ]; then
    tar -xf "${JAVA_JAR_DIR}/${JAVA_BUILD_ARTIFACT}"
    mv tdf3-lib-java/*.jar "${JAVA_JAR_DIR}"/
    rm -rf "${JAVA_JAR_DIR:?}/${JAVA_BUILD_ARTIFACT:?}"
    rm -rf tdf3-lib-java
  fi

else
  monolog DEBUG "Found jars in [${JAVA_JAR_DIR}] - [$(ls -l "${JAVA_JAR_DIR}")]"
fi

find "${JAVA_JAR_DIR}" -name "*.jar" -exec chmod guo+rx {} \;

# Build the script
monolog DEBUG "Building cli class file [${JAVA_CLI_DIR}/osstdf3.java]"
if ! javac -cp ":${JAVA_JAR_DIR}/*" "${JAVA_CLI_DIR}/osstdf3.java"; then
  monolog ERROR "Failed to compile [${JAVA_CLI_DIR}/osstdf3.java]"
  exit 1
fi

_cleanup() {
  monolog TRACE "(_cleanup) Removing [${JAVA_CLI_DIR}/*.class]"
  rm -f "${JAVA_CLI_DIR}/*.class"
}
export -f _cleanup
trap _cleanup EXIT

OWNER=$1
shift

STAGE=$1
shift

ACTION=$1
shift

SOURCE=$1
shift

TARGET=$1
shift

if [[ $TDF3_CERT_AUTHORITY && ! $CERT_CLIENT_BASE ]]; then
  # shellcheck disable=SC2001
  cn=$(sed 's/^CN=\([^,]*\).*/\1/' <<<"$OWNER")
  if [ -f "${PROJECT_ROOT}/xtest/${cn}.crt" ]; then
    export CERT_CLIENT_BASE="${PROJECT_ROOT}/xtest/${cn}"
  else
    export CERT_CLIENT_BASE="${PROJECT_ROOT}/certs/${cn}"
  fi
  monolog DEBUG "CERT_CLIENT_BASE=${CERT_CLIENT_BASE}"
fi

java -cp "${JAVA_CLI_DIR}:${JAVA_JAR_DIR}/*" osstdf3 "$STAGE" "$SOURCE" "$TARGET" "$OWNER" "$ACTION" "${@}"
