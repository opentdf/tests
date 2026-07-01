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
import hashlib
import json
import os
import secrets
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

import tdfs
from abac import Attribute
from audit_logs import AuditLogAsserter
from fixtures.encryption import EncryptFactory


def _token_endpoint() -> str:
    if endpoint := os.getenv("TOKENENDPOINT"):
        return endpoint
    kc_full_url = os.getenv(
        "KCFULLURL",
        f"{os.getenv('KCHOST', 'http://localhost:8888')}/auth/realms/{os.getenv('REALM', 'opentdf')}",
    )
    return f"{kc_full_url}/protocol/openid-connect/token"


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_int(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    return _b64u(value.to_bytes(length, "big"))


def _jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        raise AssertionError("expected access token to be a JWT")
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def _sign_jwt(
    private_key: RSAPrivateKey,
    header: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> str:
    header_b64 = _b64u(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode()
    )
    payload_b64 = _b64u(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    )
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header_b64}.{payload_b64}.{_b64u(signature)}"


def time_now() -> int:
    return int(time.time())


@dataclass(frozen=True)
class DPoPKey:
    private_key: RSAPrivateKey
    public_jwk: dict[str, str]

    @classmethod
    def generate(cls) -> DPoPKey:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_numbers = private_key.public_key().public_numbers()
        return cls(
            private_key=private_key,
            public_jwk={
                "kty": "RSA",
                "n": _b64u_int(public_numbers.n),
                "e": _b64u_int(public_numbers.e),
            },
        )

    @property
    def thumbprint(self) -> str:
        # RFC 7638 canonical member set for RSA public keys.
        canonical = json.dumps(
            {
                "e": self.public_jwk["e"],
                "kty": self.public_jwk["kty"],
                "n": self.public_jwk["n"],
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        return _b64u(hashlib.sha256(canonical).digest())

    @property
    def public_pem(self) -> str:
        return (
            self.private_key.public_key()
            .public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("ascii")
        )

    def sign(self, payload: Mapping[str, Any], typ: str = "JWT") -> str:
        return _sign_jwt(
            self.private_key,
            {"alg": "RS256", "typ": typ},
            payload,
        )

    def sign_dpop_proof(
        self,
        *,
        htm: str,
        htu: str,
        access_token: str | None = None,
        nonce: str | None = None,
        jti: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "htm": htm,
            "htu": htu,
            "iat": int(time_now()),
            "jti": jti or str(uuid.uuid4()),
        }
        if access_token is not None:
            payload["ath"] = _b64u(
                hashlib.sha256(access_token.encode("ascii")).digest()
            )
        if nonce is not None:
            payload["nonce"] = nonce
        return _sign_jwt(
            self.private_key,
            {
                "alg": "RS256",
                "jwk": self.public_jwk,
                "typ": "dpop+jwt",
            },
            payload,
        )


@dataclass(frozen=True)
class DPoPAccessToken:
    token: str
    key: DPoPKey


@dataclass(frozen=True)
class RewrapCall:
    url: str
    headers: dict[str, str]
    body: str


def _get_dpop_access_token() -> DPoPAccessToken:
    key = DPoPKey.generate()
    token_endpoint = _token_endpoint()
    # The dpop-bound client is provisioned alongside the default `opentdf`
    # client by `service provision keycloak`. We default to it here so tests
    # that mint DPoP-bound tokens via Keycloak don't need extra env wiring.
    client_id = os.getenv("CLIENTID", "opentdf-dpop")
    client_secret = os.getenv("CLIENTSECRET", "secret")

    def post_token(nonce: str | None = None) -> requests.Response:
        proof = key.sign_dpop_proof(
            htm="POST",
            htu=token_endpoint,
            nonce=nonce,
        )
        return requests.post(
            token_endpoint,
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "DPoP": proof,
            },
            timeout=15,
        )

    response = post_token()
    nonce = response.headers.get("DPoP-Nonce")
    if response.status_code == 400 and nonce:
        response = post_token(nonce)

    assert response.status_code == 200, response.text
    body = response.json()
    if body.get("token_type") != "DPoP":
        pytest.skip(
            f"Keycloak realm not configured for DPoP (token_type={body.get('token_type')!r}); "
            "set the realm's OAuth client to require DPoP-bound tokens"
        )
    access_token = body["access_token"]

    token_payload = _jwt_payload(access_token)
    assert token_payload.get("cnf", {}).get("jkt") == key.thumbprint
    return DPoPAccessToken(token=access_token, key=key)


def _connect_rewrap_url(kas_url: str) -> str:
    parsed = urlparse(kas_url)
    return f"{parsed.scheme}://{parsed.netloc}/kas.AccessService/Rewrap"


def _rewrap_request_body(
    tdf_file: Path, session_public_key_pem: str
) -> tuple[str, str]:
    manifest = tdfs.manifest(tdf_file)
    kao = manifest.encryptionInformation.keyAccess[0]
    # KeyAccessObject's Pydantic field names already match Connect-RPC's JSON
    # shape for kas.proto's KeyAccess message; the extra tdf_spec_version
    # field is ignored by the platform's lenient decoder.
    request_body = {
        "clientPublicKey": session_public_key_pem,
        "requests": [
            {
                "keyAccessObjects": [
                    {
                        "keyAccessObjectId": "kao-0",
                        "keyAccessObject": kao.model_dump(exclude_none=True),
                    }
                ],
                "policy": {
                    "id": "policy",
                    "body": manifest.encryptionInformation.policy,
                },
            }
        ],
    }
    return kao.url, json.dumps(request_body, separators=(",", ":"), sort_keys=True)


def _signed_rewrap_request(tdf_file: Path, key: DPoPKey) -> RewrapCall:
    kas_url, request_body = _rewrap_request_body(tdf_file, key.public_pem)
    now = time_now()
    signed_request_token = key.sign(
        {
            "exp": now + 60,
            "iat": now,
            "requestBody": request_body,
        }
    )
    additional_context = base64.b64encode(
        json.dumps(
            {"obligations": {"fulfillableFQNs": []}},
            separators=(",", ":"),
        ).encode("ascii")
    ).decode("ascii")
    return RewrapCall(
        url=_connect_rewrap_url(kas_url),
        headers={
            "Accept": "application/json",
            "Connect-Protocol-Version": "1",
            "Content-Type": "application/json",
            "X-Rewrap-Additional-Context": additional_context,
        },
        body=json.dumps({"signedRequestToken": signed_request_token}),
    )


def _post_rewrap(
    call: RewrapCall,
    *,
    access_token: str,
    dpop_proof: str | None,
    auth_scheme: str = "DPoP",
) -> requests.Response:
    headers = dict(call.headers)
    headers["Authorization"] = f"{auth_scheme} {access_token}"
    if dpop_proof is not None:
        headers["DPoP"] = dpop_proof
    return requests.post(
        call.url,
        data=call.body,
        headers=headers,
        timeout=15,
    )


def _post_rewrap_with_nonce_retry(
    call: RewrapCall,
    key: DPoPKey,
    *,
    access_token: str,
    auth_scheme: str = "DPoP",
) -> requests.Response:
    """POST a rewrap, transparently satisfying a `require_nonce` challenge.

    Mints a fresh DPoP proof (no nonce) and sends it. If the KAS replies with a
    `401` carrying a `DPoP-Nonce` header (the `use_dpop_nonce` challenge), the
    proof is re-minted with that nonce and the request is retried once, keeping
    the same `auth_scheme`. This makes callers agnostic to whether
    `require_nonce` is enabled on the target KAS: with it off the first request
    is returned as-is; with it on the second (nonce-bearing) request is.
    """
    proof = key.sign_dpop_proof(htm="POST", htu=call.url, access_token=access_token)
    response = _post_rewrap(
        call, access_token=access_token, dpop_proof=proof, auth_scheme=auth_scheme
    )
    nonce = response.headers.get("DPoP-Nonce")
    if response.status_code == 401 and nonce:
        proof = key.sign_dpop_proof(
            htm="POST", htu=call.url, access_token=access_token, nonce=nonce
        )
        response = _post_rewrap(
            call, access_token=access_token, dpop_proof=proof, auth_scheme=auth_scheme
        )
    return response


def _assert_unauthorized(response: requests.Response) -> None:
    assert response.status_code == 401, response.text
    # Confirm the rejection is actually a DPoP-related challenge so a 401
    # from an unrelated misconfiguration doesn't silently "pass" the test.
    auth = response.headers.get("WWW-Authenticate", "")
    assert auth.startswith("DPoP"), f"expected DPoP challenge, got: {auth!r}"


def _skip_unless_dpop_enabled(encrypt_sdk: tdfs.SDK, in_focus: set[tdfs.SDK]) -> None:
    if encrypt_sdk not in in_focus:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("dpop")
    encrypt_sdk.skip_if_unsupported("dpop")


@pytest.fixture(autouse=True)
def _dpop_client_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # SDK CLI shims read CLIENTID/XT_WITH_DPOP from the environment; tests in
    # this module must use the DPoP-bound client provisioned by
    # `service provision keycloak` and enable DPoP proof generation.
    monkeypatch.setenv("CLIENTID", "opentdf-dpop")
    monkeypatch.setenv("XT_WITH_DPOP", "ES256")


def test_dpop_happy_path_roundtrip(
    attribute_single_kas_grant: Attribute,
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

    attr = attribute_single_kas_grant
    ct_file = encrypted_tdf(
        encrypt_sdk,
        attr_values=attr.value_fqns,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
    )
    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file, shallow=False)


def test_dpop_server_issued_nonce_retry(
    attribute_single_kas_grant: Attribute,
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
    pfs.skip_if_unsupported("dpop", "dpop_nonce_challenge")
    encrypt_sdk.skip_if_unsupported("dpop", "dpop_nonce_challenge")
    decrypt_sdk.skip_if_unsupported("dpop", "dpop_nonce_challenge")

    attr = attribute_single_kas_grant
    ct_file = encrypted_tdf(
        encrypt_sdk,
        attr_values=attr.value_fqns,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
    )
    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file, shallow=False)


def test_dpop_bearer_scheme_warns_but_accepted_for_dpop_token(
    attribute_single_kas_grant: Attribute,
    encrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    encrypted_tdf: EncryptFactory,
    audit_logs: AuditLogAsserter,
):
    """A DPoP-bound access token presented with `Authorization: Bearer` is currently
    accepted (provided a valid DPoP proof header is attached) but the platform emits
    a WARN log to surface non-compliant SDK behavior. This is the SDK-drift scenario:
    the proof is correct, only the Authorization scheme is wrong.

    Per RFC 9449 §7.1 the request SHOULD be rejected with 401. The platform's WARN
    is the deliberate intermediate state while SDKs are brought into compliance.

    TODO(DSPX-3573): once all SDKs send the correct DPoP scheme, flip this test:
      - drop the WARN assertion
      - assert the Bearer-scheme call is rejected with 401 + WWW-Authenticate: DPoP
      - rename to test_dpop_rejects_bearer_scheme_on_dpop_token
    """
    _skip_unless_dpop_enabled(encrypt_sdk, in_focus)

    attr = attribute_single_kas_grant
    ct_file = encrypted_tdf(encrypt_sdk, attr_values=attr.value_fqns)
    dpop_access = _get_dpop_access_token()
    rewrap_call = _signed_rewrap_request(ct_file, dpop_access.key)

    # Both calls go through the nonce-retry helper so the test passes whether or
    # not the target KAS has `require_nonce` enabled: when it is, the lenient
    # accept (and the WARN) only happen after the nonce challenge is satisfied.
    mark = audit_logs.mark("before_bearer_scheme_request")
    bearer_response = _post_rewrap_with_nonce_retry(
        rewrap_call,
        dpop_access.key,
        access_token=dpop_access.token,
        auth_scheme="Bearer",
    )

    # Current (lenient) behavior: accepted. Will become 401 under DSPX-3573.
    assert bearer_response.status_code == 200, bearer_response.text
    audit_logs.assert_contains(
        r"DPoP-bound access token presented under Bearer Authorization scheme",
        since_mark=mark,
    )

    # Compliant path control: same proof key, same token, just the right scheme.
    dpop_response = _post_rewrap_with_nonce_retry(
        rewrap_call,
        dpop_access.key,
        access_token=dpop_access.token,
        auth_scheme="DPoP",
    )
    assert dpop_response.status_code == 200, dpop_response.text


def test_dpop_rejects_tampered_proof_htu(
    attribute_single_kas_grant: Attribute,
    encrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    encrypted_tdf: EncryptFactory,
):
    """A DPoP proof whose `htu` claim does not match the request URI MUST be rejected."""
    _skip_unless_dpop_enabled(encrypt_sdk, in_focus)

    attr = attribute_single_kas_grant
    ct_file = encrypted_tdf(encrypt_sdk, attr_values=attr.value_fqns)
    dpop_access = _get_dpop_access_token()
    rewrap_call = _signed_rewrap_request(ct_file, dpop_access.key)
    # Well-formed full URL pointing at a wrong path — exercises "tampered to
    # a valid-shape but wrong endpoint" rather than "malformed string".
    tampered_htu = rewrap_call.url.replace("/Rewrap", "/WrongRewrap")
    assert tampered_htu != rewrap_call.url, "htu tamper must actually differ"
    proof = dpop_access.key.sign_dpop_proof(
        htm="POST",
        htu=tampered_htu,
        access_token=dpop_access.token,
    )

    response = _post_rewrap(
        rewrap_call,
        access_token=dpop_access.token,
        dpop_proof=proof,
    )

    _assert_unauthorized(response)


def test_dpop_rejects_replayed_jti(
    attribute_single_kas_grant: Attribute,
    encrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    encrypted_tdf: EncryptFactory,
):
    """Replaying a DPoP proof `jti` MUST be rejected — both as a byte-identical
    replay and as a freshly signed proof reusing the known jti (RFC 9449 §11.1).
    """
    _skip_unless_dpop_enabled(encrypt_sdk, in_focus)

    attr = attribute_single_kas_grant
    ct_file = encrypted_tdf(encrypt_sdk, attr_values=attr.value_fqns)
    dpop_access = _get_dpop_access_token()
    rewrap_call = _signed_rewrap_request(ct_file, dpop_access.key)

    replayed_jti = f"xtest-{secrets.token_urlsafe(16)}"
    proof = dpop_access.key.sign_dpop_proof(
        htm="POST",
        htu=rewrap_call.url,
        access_token=dpop_access.token,
        jti=replayed_jti,
    )
    first = _post_rewrap(
        rewrap_call,
        access_token=dpop_access.token,
        dpop_proof=proof,
    )
    nonce = first.headers.get("DPoP-Nonce")
    if first.status_code == 401 and nonce:
        # KAS is enforcing nonces — retry once with the issued nonce.
        proof = dpop_access.key.sign_dpop_proof(
            htm="POST",
            htu=rewrap_call.url,
            access_token=dpop_access.token,
            nonce=nonce,
            jti=replayed_jti,
        )
        first = _post_rewrap(
            rewrap_call,
            access_token=dpop_access.token,
            dpop_proof=proof,
        )

    assert first.status_code == 200, first.text

    # 1. Byte-identical replay of the accepted proof.
    second = _post_rewrap(
        rewrap_call,
        access_token=dpop_access.token,
        dpop_proof=proof,
    )
    _assert_unauthorized(second)

    # 2. Fresh proof reusing the same jti — the server must remember jti values
    # across requests, not just deduplicate identical bytes.
    fresh_proof_same_jti = dpop_access.key.sign_dpop_proof(
        htm="POST",
        htu=rewrap_call.url,
        access_token=dpop_access.token,
        nonce=nonce,
        jti=replayed_jti,
    )
    third = _post_rewrap(
        rewrap_call,
        access_token=dpop_access.token,
        dpop_proof=fresh_proof_same_jti,
    )
    _assert_unauthorized(third)


def test_dpop_rejects_tampered_nonce(
    attribute_single_kas_grant: Attribute,
    encrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    encrypted_tdf: EncryptFactory,
):
    """When `require_nonce: true`, a tampered nonce MUST 401 with a fresh DPoP-Nonce."""
    _skip_unless_dpop_enabled(encrypt_sdk, in_focus)
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("dpop", "dpop_nonce_challenge")

    attr = attribute_single_kas_grant
    ct_file = encrypted_tdf(encrypt_sdk, attr_values=attr.value_fqns)
    dpop_access = _get_dpop_access_token()
    rewrap_call = _signed_rewrap_request(ct_file, dpop_access.key)

    initial_proof = dpop_access.key.sign_dpop_proof(
        htm="POST",
        htu=rewrap_call.url,
        access_token=dpop_access.token,
    )
    challenge = _post_rewrap(
        rewrap_call,
        access_token=dpop_access.token,
        dpop_proof=initial_proof,
    )
    issued_nonce = challenge.headers.get("DPoP-Nonce")
    assert challenge.status_code == 401 and issued_nonce is not None, (
        "Expected initial request to be challenged with 401 + DPoP-Nonce, got: "
        f"{challenge.status_code} + {challenge.headers}"
    )

    tampered_proof = dpop_access.key.sign_dpop_proof(
        htm="POST",
        htu=rewrap_call.url,
        access_token=dpop_access.token,
        nonce=f"tampered-{issued_nonce}",
    )
    response = _post_rewrap(
        rewrap_call,
        access_token=dpop_access.token,
        dpop_proof=tampered_proof,
    )

    _assert_unauthorized(response)
    assert response.headers.get("DPoP-Nonce")
