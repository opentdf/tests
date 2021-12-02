#!/usr/bin/env python

import sys
import json
import requests
from pprint import pprint

KEYCLOAK_HOST = sys.argv[1]
REALM = sys.argv[2]

url = "{}/auth/realms/{}".format(KEYCLOAK_HOST, REALM)
response = requests.get(url, headers={"Content-Type": "application/json"})
resp_json = json.loads(response.text)
keycloak_public_key = (
    "-----BEGIN PUBLIC KEY-----\n"
    + resp_json["public_key"]
    + "\n"
    + "-----END PUBLIC KEY-----\n"
)
print("# KEYCLOAK public key")
print(keycloak_public_key)

with open(f"keycloak-public-{REALM}.pem", "w") as data:
    data.write(keycloak_public_key)
