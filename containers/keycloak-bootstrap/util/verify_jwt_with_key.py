#!/usr/bin/env python

import sys
import jwt
from pprint import pprint
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend


with open(sys.argv[1], "rb") as data:
    pem_bytes = data.read()

public_key = serialization.load_pem_public_key(pem_bytes, backend=default_backend())

decoded = jwt.decode(sys.argv[2], public_key, algorithms=["RS256"])
pprint(decoded)
