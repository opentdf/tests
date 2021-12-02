#!/usr/bin/env python3

import jwt
import sys
import json
import requests
from pprint import pprint

my_jwt = sys.stdin.read()
parsed_jwt = json.loads(my_jwt)
access_token = parsed_jwt["access_token"]

# grab information out of the token without verifying it.
decoded = jwt.decode(access_token, options={"verify_signature": False})
pprint(decoded)
issuer_url = decoded["iss"]
audience = decoded["aud"]

unverified_headers = jwt.get_unverified_header(access_token)
algorithms = unverified_headers["alg"]

pub_key_json = requests.get(issuer_url)
pub_key_info = json.loads(pub_key_json.text)

# N.B.  You actually need the whitespace for this to work.
KEYCLOAK_PUBLIC_KEY = (
    "-----BEGIN PUBLIC KEY-----\n" + pub_key_info["public_key"] + "\n"
    "-----END PUBLIC KEY-----"
)

decoded = jwt.decode(
    access_token, KEYCLOAK_PUBLIC_KEY, audience=audience, algorithms=algorithms
)

pprint(decoded)
