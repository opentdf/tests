"""TDF assertion fixtures for testing assertion signing and verification.

This module contains fixtures for:
- Generating signing keys (HS256, RS256)
- Creating assertion files with various signing configurations
- Creating assertion verification key files
"""

import pytest
import base64
import secrets
import json
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from pathlib import Path
from pydantic_core import to_jsonable_python

import assertions


@pytest.fixture(scope="package")
def hs256_key() -> str:
    """Generate a random HS256 (HMAC-SHA256) signing key."""
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


@pytest.fixture(scope="package")
def rs256_keys() -> tuple[str, str]:
    """Generate an RS256 (RSA-SHA256) key pair.

    Returns:
        tuple[str, str]: (private_key_pem, public_key_pem)
    """
    # Generate an RSA private key
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Generate the public key from the private key
    public_key = private_key.public_key()

    # Serialize the private key to PEM format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Serialize the public key to PEM format
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # Convert to string with escaped newlines
    private_pem_str = private_pem.decode("utf-8")
    public_pem_str = public_pem.decode("utf-8")

    return private_pem_str, public_pem_str


def write_assertion_to_file(
    tmp_dir: Path, file_name: str, assertion_list: list[assertions.Assertion] = []
) -> Path:
    """Write assertion list to a JSON file."""
    as_file = tmp_dir / f"test-assertion-{file_name}.json"
    assertion_json = json.dumps(to_jsonable_python(assertion_list, exclude_none=True))
    with as_file.open("w") as f:
        f.write(assertion_json)
    return as_file


def write_assertion_verification_keys_to_file(
    tmp_dir: Path,
    file_name: str,
    assertion_verification_keys: assertions.AssertionVerificationKeys,
) -> Path:
    """Write assertion verification keys to a JSON file."""
    as_file = tmp_dir / f"test-assertion-verification-{file_name}.json"
    assertion_verification_json = json.dumps(
        to_jsonable_python(assertion_verification_keys, exclude_none=True)
    )
    with as_file.open("w") as f:
        f.write(assertion_verification_json)
    return as_file


@pytest.fixture(scope="package")
def assertion_file_no_keys(tmp_dir: Path) -> Path:
    """Assertion file with a single handling assertion (no signing key)."""
    assertion_list = [
        assertions.Assertion(
            appliesToState="encrypted",
            id="424ff3a3-50ca-4f01-a2ae-ef851cd3cac0",
            scope="tdo",
            statement=assertions.Statement(
                format="json+stanag5636",
                schema="urn:nato:stanag:5636:A:1:elements:json",
                value='{"ocl":{"pol":"62c76c68-d73d-4628-8ccc-4c1e18118c22","cls":"SECRET","catl":[{"type":"P","name":"Releasable To","vals":["usa"]}],"dcr":"2024-10-21T20:47:36Z"},"context":{"[@base](https://github.com/base)":"urn:nato:stanag:5636:A:1:elements:json"}}',
            ),
            type="handling",
        )
    ]
    return write_assertion_to_file(
        tmp_dir, "assertion_1_no_signing_key", assertion_list
    )


@pytest.fixture(scope="package")
def assertion_file_rs_and_hs_keys(
    tmp_dir: Path, hs256_key: str, rs256_keys: tuple[str, str]
) -> Path:
    """Assertion file with two handling assertions (HS256 and RS256 signing keys)."""
    rs256_private, _ = rs256_keys
    assertion_list = [
        assertions.Assertion(
            appliesToState="encrypted",
            id="assertion1",
            scope="tdo",
            statement=assertions.Statement(
                format="json+stanag5636",
                schema="urn:nato:stanag:5636:A:1:elements:json",
                value='{"ocl":{"pol":"62c76c68-d73d-4628-8ccc-4c1e18118c22","cls":"SECRET","catl":[{"type":"P","name":"Releasable To","vals":["usa"]}],"dcr":"2024-10-21T20:47:36Z"},"context":{"[@base](https://github.com/base)":"urn:nato:stanag:5636:A:1:elements:json"}}',
            ),
            type="handling",
            signingKey=assertions.AssertionKey(
                alg="HS256",
                key=hs256_key,
            ),
        ),
        assertions.Assertion(
            appliesToState="encrypted",
            id="assertion2",
            scope="tdo",
            statement=assertions.Statement(
                format="json+stanag5636",
                schema="urn:nato:stanag:5636:A:1:elements:json",
                value='{"ocl":{"pol":"62c76c68-d73d-4628-8ccc-4c1e18118c22","cls":"SECRET","catl":[{"type":"P","name":"Releasable To","vals":["usa"]}],"dcr":"2024-10-21T20:47:36Z"},"context":{"[@base](https://github.com/base)":"urn:nato:stanag:5636:A:1:elements:json"}}',
            ),
            type="handling",
            signingKey=assertions.AssertionKey(
                alg="RS256",
                key=rs256_private,
            ),
        ),
    ]
    return write_assertion_to_file(
        tmp_dir, "assertion1_hs_assertion2_rs", assertion_list
    )


@pytest.fixture(scope="package")
def assertion_verification_file_rs_and_hs_keys(
    tmp_dir: Path, hs256_key: str, rs256_keys: tuple[str, str]
) -> Path:
    """Assertion verification file with HS256 and RS256 public keys."""
    _, rs256_public = rs256_keys
    assertion_verification = assertions.AssertionVerificationKeys(
        keys={
            "assertion1": assertions.AssertionKey(
                alg="HS256",
                key=hs256_key,
            ),
            "assertion2": assertions.AssertionKey(
                alg="RS256",
                key=rs256_public,
            ),
        }
    )
    return write_assertion_verification_keys_to_file(
        tmp_dir, "assertion1_hs_assertion2_rs", assertion_verification
    )
