#!/usr/bin/env bash
# shellcheck disable=SC2206,SC1091

# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <nano>
#
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# shellcheck source=../../test.env
source "$SCRIPT_DIR"/../../test.env

args=(
  -o "$3"
  --host "$PLATFORMURL"
  --tls-no-verify
  --log-level debug
  --with-client-creds '{"clientId":"'$CLIENTID'","clientSecret":"'$CLIENTSECRET'"}'
)
if [ "$4" == "nano" ]; then
    args+=(--tdf-type "$4")
fi
if [ "$1" == "encrypt" ]; then
   echo "$SCRIPT_DIR"/otdfctl encrypt "${args[@]}" "$2"  
   "$SCRIPT_DIR"/otdfctl encrypt "${args[@]}" "$2" 
elif [ "$1" == "decrypt" ]; then
    "$SCRIPT_DIR"/otdfctl decrypt "${args[@]}" "$2"
else
    echo "Incorrect argument provided"
    exit 1
fi
