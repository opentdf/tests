#!/usr/bin/env bash

# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <nano>
#
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source "$SCRIPT_DIR"/../../test.env

args=(
  -o "$3"
  --host "$KASURL"
  --tls-no-verify
  --log-level debug
  --with-client-creds '{"clientId":"'$CLIENTID'","clientSecret":"'$CLIENTSECRET'"}'
)
if [ "$4" == "True" ]; then
    args+=(--tdf-type nano)
fi
if [ "$1" == "encrypt" ]; then
   echo $SCRIPT_DIR/otdfctl encrypt "${args[@]}" "$2"  
   $SCRIPT_DIR/otdfctl encrypt "${args[@]}" "$2" 
elif [ "$1" == "decrypt" ]; then
    $SCRIPT_DIR/otdfctl decrypt "${args[@]}" "$2"
else
    echo "Incorrect argument provided"
    exit 1
fi

