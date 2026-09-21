"""KAS (Key Access Service) registry and entry fixtures.

This module contains fixtures for setting up KAS instances used in testing:
- Default KAS (localhost:8080)
- Named KAS instances matching CI workflow (alpha, beta, gamma, delta)
- Key management KAS instances (km1, km2, and dedicated KAO-enabled km3)
"""

import logging
import os
import urllib.error
import urllib.parse
import urllib.request

import pytest

import abac
import tdfs
from otdfctl import OpentdfCommandLineTool

logger = logging.getLogger("xtest")

PLATFORM_DIR = os.getenv("PLATFORM_DIR", "../../platform")

HEALTH_TIMEOUT_S = 5


def kas_health_error(kas_url: str) -> str | None:
    """Describe why no KAS is answering at ``kas_url``, or None if one is.

    The registry fixtures never touch the KAS itself -- ``kas_registry_create_if_not_present``
    and ``_get_or_create_key`` talk only to the policy service on PLATFORMURL. So a KAS that
    was never started stays invisible right up until a rewrap, where it surfaces as a
    connection refused buried in an SDK CLI's stderr. Probing ``/healthz`` first turns that
    into a message naming the port and the reason, which is why this returns the reason
    rather than a bool.

    ``/healthz`` is served from the root, so any path on ``kas_url`` -- ``/kas`` for most of
    these -- is deliberately dropped.

    Raises:
        ValueError: if ``kas_url`` is not an absolute http(s) URL.
    """
    parsed = urllib.parse.urlparse(kas_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        # Left alone, a typo'd KASURL7 becomes "://healthz", fails to connect, and
        # reports itself as an unreachable KAS -- sending you to debug a service that
        # is running fine. The URL is the bug, so say so.
        raise ValueError(
            f"not a usable KAS URL: {kas_url!r} "
            "(expected an absolute URL, e.g. http://localhost:8787)"
        )

    url = f"{parsed.scheme}://{parsed.netloc}/healthz"
    # No proxy: these are loopback services, and an http_proxy inherited from the
    # environment would have the probe report on the proxy's health instead.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=HEALTH_TIMEOUT_S) as resp:
            if resp.status != 200:
                return f"{url} returned HTTP {resp.status}"
            return None
    except (urllib.error.URLError, TimeoutError) as e:
        # Only connection-shaped failures mean "no KAS here". Anything else is a bug
        # in this probe and should reach the caller as one.
        logger.debug("KAS health probe at %s failed: %s", url, e)
        return f"{url}: {e}"


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


@pytest.fixture(scope="session")
def kas_url_km3():
    """URL for the dedicated KAO-enabled key management KAS instance (km3)."""
    return os.getenv("KASURL7", "http://localhost:8787")


def require_km3(kas_url: str) -> None:
    """Skip if the platform can't do KAO-URI lookup; fail if it can but km3 is absent.

    Two gates, deliberately with different outcomes. The feature gate answers "was
    the override set?" -- a build that doesn't do this is not a failure, so it
    skips. Past that the caller has said to run these tests, so a km3 that isn't
    listening is a broken environment, and reporting it as a second skip would make
    a mistyped KASURL7 read exactly like a correct "this build can't do it". pytest
    prints captured logs for errors but not for skips, so the skip is also the
    harder of the two to diagnose after the fact.
    """
    tdfs.get_platform_features().skip_if_unsupported(
        "key_management", "kas_uri_from_kao"
    )
    if reason := kas_health_error(kas_url):
        pytest.fail(
            f"km3 KAS is not answering ({reason}). Start one with `otdf-local up`, "
            "point KASURL7 at it, or drop kas_uri_from_kao from "
            "XT_FORCE_PLATFORM_SUPPORTS to skip these tests instead.",
            pytrace=False,
        )


@pytest.fixture(scope="module")
def kas_entry_km3(otdfctl: OpentdfCommandLineTool, kas_url_km3: str) -> abac.KasEntry:
    """KAS registry entry for the dedicated KAO-enabled key management KAS km3."""
    require_km3(kas_url_km3)
    return otdfctl.kas_registry_create_if_not_present(kas_url_km3)
