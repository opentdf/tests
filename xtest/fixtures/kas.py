"""KAS (Key Access Service) registry and entry fixtures.

This module contains fixtures for setting up KAS instances used in testing:
- Default KAS (localhost:8080)
- Named KAS instances matching CI workflow (alpha, beta, gamma, delta)
- Key management KAS instances (km1, km2)
"""

import os

import pytest

import abac
from otdfctl import OpentdfCommandLineTool

PLATFORM_DIR = os.getenv("PLATFORM_DIR", "../../platform")


def load_cached_kas_keys() -> abac.PublicKey:
    """Load RSA and EC public keys from platform directory."""
    keyset: list[abac.KasPublicKey] = []
    with open(f"{PLATFORM_DIR}/kas-cert.pem") as rsaFile:
        keyset.append(
            abac.KasPublicKey(
                alg=abac.KAS_PUBLIC_KEY_ALG_ENUM_RSA_2048,
                kid="r1",
                pem=rsaFile.read(),
            )
        )
    with open(f"{PLATFORM_DIR}/kas-ec-cert.pem") as ecFile:
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
    with open(f"{PLATFORM_DIR}/kas-cert.pem") as rsaFile:
        return abac.KasPublicKey(
            algStr="rsa:2048",
            kid="r1",
            pem=rsaFile.read(),
        )


@pytest.fixture(scope="session")
def kas_public_key_e1() -> abac.KasPublicKey:
    """EC secp256r1 public key (kid='e1') for KAS."""
    with open(f"{PLATFORM_DIR}/kas-ec-cert.pem") as ecFile:
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
    otdfctl: OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_default: str,
) -> abac.KasEntry:
    """KAS registry entry for default KAS."""
    return otdfctl.kas_registry_create_if_not_present(kas_url_default, cached_kas_keys)


# Alpha KAS (localhost:8181) - KASURL1
@pytest.fixture(scope="session")
def kas_url_alpha():
    """URL for alpha KAS instance."""
    return os.getenv("KASURL1", "http://localhost:8181/kas")


@pytest.fixture(scope="module")
def kas_entry_alpha(
    otdfctl: OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_alpha: str,
) -> abac.KasEntry:
    """KAS registry entry for alpha KAS."""
    return otdfctl.kas_registry_create_if_not_present(kas_url_alpha, cached_kas_keys)


# Beta KAS (localhost:8282) - KASURL2
@pytest.fixture(scope="session")
def kas_url_beta():
    """URL for beta KAS instance."""
    return os.getenv("KASURL2", "http://localhost:8282/kas")


@pytest.fixture(scope="module")
def kas_entry_beta(
    otdfctl: OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_beta: str,
) -> abac.KasEntry:
    """KAS registry entry for beta KAS."""
    return otdfctl.kas_registry_create_if_not_present(kas_url_beta, cached_kas_keys)


# Gamma KAS (localhost:8383) - KASURL3, used for attribute-level grants
@pytest.fixture(scope="session")
def kas_url_gamma():
    """URL for gamma KAS instance."""
    return os.getenv("KASURL3", "http://localhost:8383/kas")


@pytest.fixture(scope="module")
def kas_entry_gamma(
    otdfctl: OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_gamma: str,
) -> abac.KasEntry:
    """KAS registry entry for gamma KAS.

    Use this for attribute-scoped key mappings and grants
    so we can easily verify when a key was assigned from its attribute default,
    and not a value mapping.
    """
    return otdfctl.kas_registry_create_if_not_present(kas_url_gamma, cached_kas_keys)


# Delta KAS (localhost:8484) - KASURL4, used for namespace-level grants
@pytest.fixture(scope="session")
def kas_url_delta():
    """URL for delta KAS instance."""
    return os.getenv("KASURL4", "http://localhost:8484/kas")


@pytest.fixture(scope="module")
def kas_entry_delta(
    otdfctl: OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_delta: str,
) -> abac.KasEntry:
    """KAS registry entry for delta KAS.

    Use this for namespace-scoped key mappings and grants
    so we can easily verify when a key was assigned from its namespace default.
    """
    return otdfctl.kas_registry_create_if_not_present(kas_url_delta, cached_kas_keys)


# Key management KAS instances
@pytest.fixture(scope="session")
def kas_url_km1():
    """URL for first key management KAS instance (km1)."""
    return os.getenv("KASURL5", "http://localhost:8585")


@pytest.fixture(scope="module")
def kas_entry_km1(
    otdfctl: OpentdfCommandLineTool,
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
    otdfctl: OpentdfCommandLineTool,
    kas_url_km2: str,
) -> abac.KasEntry:
    """KAS registry entry for key management KAS km2."""
    return otdfctl.kas_registry_create_if_not_present(kas_url_km2)
