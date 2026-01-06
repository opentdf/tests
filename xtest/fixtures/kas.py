"""KAS (Key Access Service) registry and entry fixtures.

This module contains fixtures for setting up KAS instances used in testing:
- Default KAS (localhost:8080)
- Value-specific KAS instances (value1, value2)
- Attribute-level KAS (attr)
- Namespace-level KAS (ns)
- Key management KAS instances (km1, km2)
"""
import os
import pytest
import abac
from pathlib import Path


PLATFORM_DIR = os.getenv("PLATFORM_DIR", "../../platform")


def load_cached_kas_keys() -> abac.PublicKey:
    """Load RSA and EC public keys from platform directory."""
    keyset: list[abac.KasPublicKey] = []
    with open(f"{PLATFORM_DIR}/kas-cert.pem", "r") as rsaFile:
        keyset.append(
            abac.KasPublicKey(
                alg=abac.KAS_PUBLIC_KEY_ALG_ENUM_RSA_2048,
                kid="r1",
                pem=rsaFile.read(),
            )
        )
    with open(f"{PLATFORM_DIR}/kas-ec-cert.pem", "r") as ecFile:
        keyset.append(
            abac.KasPublicKey(
                alg=abac.KAS_PUBLIC_KEY_ALG_ENUM_EC_SECP256R1,
                kid="e1",
                pem=ecFile.read(),
            )
        )
    return abac.PublicKey(
        cached=abac.KasPublicKeySet(
            keys=keyset,
        )
    )


@pytest.fixture(scope="module")
def cached_kas_keys() -> abac.PublicKey:
    """Cached KAS public keys (RSA and EC) from platform."""
    return load_cached_kas_keys()


@pytest.fixture(scope="session")
def kas_public_key_r1() -> abac.KasPublicKey:
    """RSA-2048 public key (kid='r1') for KAS."""
    with open(f"{PLATFORM_DIR}/kas-cert.pem", "r") as rsaFile:
        return abac.KasPublicKey(
            algStr="rsa:2048",
            kid="r1",
            pem=rsaFile.read(),
        )


@pytest.fixture(scope="session")
def kas_public_key_e1() -> abac.KasPublicKey:
    """EC secp256r1 public key (kid='e1') for KAS."""
    with open(f"{PLATFORM_DIR}/kas-ec-cert.pem", "r") as ecFile:
        return abac.KasPublicKey(
            algStr="ec:secp256r1",
            kid="e1",
            pem=ecFile.read(),
        )


# Default KAS (localhost:8080)
@pytest.fixture(scope="session")
def kas_url_default():
    """URL for default KAS instance."""
    return os.getenv("KASURL", "http://localhost:8080/kas")


@pytest.fixture(scope="module")
def kas_entry_default(
    otdfctl: abac.OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_default: str,
) -> abac.KasEntry:
    """KAS registry entry for default KAS."""
    return otdfctl.kas_registry_create_if_not_present(kas_url_default, cached_kas_keys)


# Value1 KAS (localhost:8181)
@pytest.fixture(scope="session")
def kas_url_value1():
    """URL for value1 KAS instance."""
    return os.getenv("KASURL1", "http://localhost:8181/kas")


@pytest.fixture(scope="module")
def kas_entry_value1(
    otdfctl: abac.OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_value1: str,
) -> abac.KasEntry:
    """KAS registry entry for value1 KAS."""
    return otdfctl.kas_registry_create_if_not_present(kas_url_value1, cached_kas_keys)


# Value2 KAS (localhost:8282)
@pytest.fixture(scope="session")
def kas_url_value2():
    """URL for value2 KAS instance."""
    return os.getenv("KASURL2", "http://localhost:8282/kas")


@pytest.fixture(scope="module")
def kas_entry_value2(
    otdfctl: abac.OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_value2: str,
) -> abac.KasEntry:
    """KAS registry entry for value2 KAS."""
    return otdfctl.kas_registry_create_if_not_present(kas_url_value2, cached_kas_keys)


# Attribute-level KAS (localhost:8383)
@pytest.fixture(scope="session")
def kas_url_attr():
    """URL for attribute-level KAS instance."""
    return os.getenv("KASURL3", "http://localhost:8383/kas")


@pytest.fixture(scope="module")
def kas_entry_attr(
    otdfctl: abac.OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_attr: str,
) -> abac.KasEntry:
    """KAS registry entry for attribute-level KAS."""
    return otdfctl.kas_registry_create_if_not_present(kas_url_attr, cached_kas_keys)


# Namespace-level KAS (localhost:8484)
@pytest.fixture(scope="session")
def kas_url_ns():
    """URL for namespace-level KAS instance."""
    return os.getenv("KASURL4", "http://localhost:8484/kas")


@pytest.fixture(scope="module")
def kas_entry_ns(
    otdfctl: abac.OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_ns: str,
) -> abac.KasEntry:
    """KAS registry entry for namespace-level KAS."""
    return otdfctl.kas_registry_create_if_not_present(kas_url_ns, cached_kas_keys)


# Key management KAS instances
@pytest.fixture(scope="session")
def kas_url_km1():
    """URL for first key management KAS instance (km1)."""
    return os.getenv("KASURL5", "http://localhost:8585")


@pytest.fixture(scope="module")
def kas_entry_km1(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url_km1: str,
) -> abac.KasEntry:
    """KAS registry entry for key management KAS km1."""
    return otdfctl.kas_registry_create_if_not_present(kas_url_km1)


@pytest.fixture(scope="session")
def kas_url_km2():
    """URL for second key management KAS instance (km2)."""
    return os.getenv("KASURL6", "http://localhost:8686")


@pytest.fixture(scope="module")
def kas_entry_km2(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url_km2: str,
) -> abac.KasEntry:
    """KAS registry entry for key management KAS km2."""
    return otdfctl.kas_registry_create_if_not_present(kas_url_km2)
