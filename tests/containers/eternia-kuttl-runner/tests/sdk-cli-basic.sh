#!/usr/bin/env bash
set -euo pipefail

printf "\nKUTTL: Cleaning up:\n'"
if [ -f ./testenc.tdf ]; then
  rm ./testenc.tdf
fi
if [ -f ./out.txt ]; then
  rm ./out.txt
fi

printf "\nKUTTL: Plaintext:\n'"
cat /testdata/secret.txt

printf "\nKUTTL: Encrypt test\n'"
bin/virtru-sdk encrypt --log-level debug --auth tdf:tdf-client:123-456 /testdata/secret.txt --out testenc.tdf

printf "\nKUTTL: Dumping contents of testenc.tdf:\n"
cat testenc.tdf

printf "\nKUTTL: Decrypt test\n"
bin/virtru-sdk decrypt --log-level debug --auth tdf:tdf-client:123-456 1>out.txt <testenc.tdf

printf "\nKUTTL: Decrypted plaintext\n"
cat out.txt
