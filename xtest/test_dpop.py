"""DPoP (RFC 9449) integration tests against a Keycloak 26 + DPoP-enforced realm.

Draft tests for DSPX-3397. They land dormant — each test skips unless both the
platform exposes `pfs.supports("dpop")` AND the participating SDK exposes
`sdk.supports("dpop")` via its cli.sh shim. As each per-repo PR lands the
required `supports dpop` case, the corresponding lane activates.

The happy-path roundtrip exercises the SDK end-to-end. The negative cases use
direct HTTP against the KAS endpoint with hand-minted proofs because the SDKs
intentionally do not expose hooks to mis-sign or tamper with their own proofs
— that's the right shape for a security test.
"""

import base64
import filecmp
import os
import time
import urllib.request
from pathlib import Path

import pytest

import tdfs
from abac import Attribute
from fixtures.encryption import EncryptFactory


def _kas_url() -> str:
    """KAS endpoint for direct-HTTP negative tests. Mirrors test.env."""
    return os.getenv(
        "KASURL", os.getenv("PLATFORMURL", "http://localhost:8080") + "/kas"
    )


def test_dpop_happy_path_roundtrip(
    attribute_single_kas_grant: tuple[Attribute, list[str]],
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    in_focus: set[tdfs.SDK],
    encrypted_tdf: EncryptFactory,
):
    """Encrypt + decrypt via a KAS that requires DPoP-bound access tokens.

    Verifies the SDK transparently:
      1. mints a DPoP proof for the token request,
      2. recognizes the resulting `token_type: DPoP`,
      3. mints a fresh DPoP proof (with `ath` claim) for the KAS rewrap,
      4. sends `Authorization: DPoP <token>` instead of `Bearer`.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("dpop")
    encrypt_sdk.skip_if_unsupported("dpop")
    decrypt_sdk.skip_if_unsupported("dpop")

    attr, _ = attribute_single_kas_grant
    ct_file = encrypted_tdf(
        encrypt_sdk,
        attr_values=attr.value_fqns,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
    )
    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_dpop_server_issued_nonce_retry(
    attribute_single_kas_grant: tuple[Attribute, list[str]],
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    in_focus: set[tdfs.SDK],
    encrypted_tdf: EncryptFactory,
):
    """Roundtrip when KAS has `services.kas.dpop.require_nonce: true`.

    The first KAS call from the SDK arrives without a `nonce` claim, so KAS
    responds 401 + `DPoP-Nonce: <opaque>`. The SDK is expected to cache the
    nonce, re-sign the proof with the nonce claim, and retry once — without
    surfacing the 401 to the caller. End result: a successful roundtrip.

    TODO(tests-cell): once a nonce-observability hook exists (KAS log line or
    response header counter), assert that exactly one 401+DPoP-Nonce challenge
    was issued and successfully retried.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("dpop")
    encrypt_sdk.skip_if_unsupported("dpop")
    decrypt_sdk.skip_if_unsupported("dpop")

    attr, _ = attribute_single_kas_grant
    ct_file = encrypted_tdf(
        encrypt_sdk,
        attr_values=attr.value_fqns,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
    )
    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@pytest.mark.skip(
    reason="TODO(tests-cell, DSPX-3397): wire up direct-HTTP DPoP negative tests once the platform-service PR lands."
)
def test_dpop_rejects_bearer_scheme_on_dpop_token():
    """A DPoP-bound access token presented with `Authorization: Bearer` MUST be rejected.

    Plan:
      1. Acquire a DPoP-bound access token (mint a proof for the token endpoint).
      2. Hit KAS /rewrap with `Authorization: Bearer <token>` and no DPoP header.
      3. Expect 401 (and a `WWW-Authenticate: DPoP error=\"invalid_token\"` challenge).
    """
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("dpop")
    pytest.fail("Not yet implemented")


@pytest.mark.skip(
    reason="TODO(tests-cell, DSPX-3397): wire up direct-HTTP DPoP negative tests once the platform-service PR lands."
)
def test_dpop_rejects_tampered_proof_htu():
    """A DPoP proof whose `htu` claim does not match the request URI MUST be rejected."""
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("dpop")
    # 1. Acquire a DPoP-bound token.
    # 2. Mint a proof with htu=https://kas.example.com/wrong-path, ath=correct.
    # 3. POST to _kas_url() + "/v2/rewrap" with that proof.
    # 4. Expect 401.
    _ = _kas_url()
    pytest.fail("Not yet implemented")


@pytest.mark.skip(
    reason="TODO(tests-cell, DSPX-3397): wire up direct-HTTP DPoP negative tests once the platform-service PR lands."
)
def test_dpop_rejects_replayed_jti():
    """Replaying the same DPoP proof `jti` MUST be rejected the second time."""
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("dpop")
    # 1. Acquire a DPoP-bound token.
    # 2. Mint a proof with a fixed jti and submit it. Expect 200.
    # 3. Submit the byte-identical proof again. Expect 401.
    pytest.fail("Not yet implemented")


@pytest.mark.skip(
    reason="TODO(tests-cell, DSPX-3397): wire up direct-HTTP DPoP negative tests once the platform-service PR lands."
)
def test_dpop_rejects_tampered_or_expired_nonce():
    """When `require_nonce: true`, an unknown/tampered/expired nonce MUST 401 with a fresh DPoP-Nonce."""
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("dpop")
    # 1. Trigger the nonce challenge (request without nonce → 401 + DPoP-Nonce).
    # 2. Submit a proof with nonce="not-the-issued-one".
    # 3. Expect 401 and a `DPoP-Nonce: <fresh>` header on the response.
    _ = time.time()
    _ = urllib.request  # silence linter on stub; used by the real impl
    _ = _b64u
    pytest.fail("Not yet implemented")
