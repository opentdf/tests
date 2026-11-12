"""Offline tests for test_dpop.py's realm check (DSPX-4333).

The DPoP roundtrips skip when the Keycloak realm hands the DPoP client plain
Bearer tokens. That check talks to Keycloak, so these stand in a fake token
endpoint and hold the skip to being a capability gap -- listed at the end of
the run -- rather than a plain skip lost among the "not in focus" ones.
"""

import base64
import json
from typing import Any

import pytest

import tdfs
import test_dpop


def _b64u_json(data: dict[str, Any]) -> str:
    raw = json.dumps(data).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _jwt(payload: dict[str, Any]) -> str:
    return f"{_b64u_json({'alg': 'none'})}.{_b64u_json(payload)}.sig"


def _proof_thumbprint(proof: str) -> str:
    header_b64 = proof.split(".")[0]
    header = json.loads(
        base64.urlsafe_b64decode(header_b64 + "=" * (-len(header_b64) % 4))
    )
    jwk = header["jwk"]
    key = test_dpop.DPoPKey(private_key=None, public_jwk=jwk)  # pyright: ignore[reportArgumentType]
    return key.thumbprint


class _FakeResponse:
    def __init__(self, status_code: int, body: dict[str, Any], headers: dict[str, str]):
        self.status_code = status_code
        self._body = body
        self.headers = headers
        self.text = json.dumps(body)

    def json(self) -> dict[str, Any]:
        return self._body


def _token_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    token_type: str,
    *,
    nonce_first: bool = False,
) -> list[dict[str, str]]:
    """Answer token requests with ``token_type``; return the headers each one sent."""
    sent: list[dict[str, str]] = []

    def post(_url: str, *, headers: dict[str, str], **_: object) -> _FakeResponse:
        sent.append(headers)
        if nonce_first and len(sent) == 1:
            return _FakeResponse(400, {"error": "use_dpop_nonce"}, {"DPoP-Nonce": "n1"})
        payload: dict[str, Any] = {"typ": token_type}
        if token_type == "DPoP":
            payload["cnf"] = {"jkt": _proof_thumbprint(headers["DPoP"])}
        body = {"access_token": _jwt(payload), "token_type": token_type}
        return _FakeResponse(200, body, {})

    monkeypatch.setattr(test_dpop.requests, "post", post)
    monkeypatch.setenv("TOKENENDPOINT", "http://kc.test/token")
    monkeypatch.setenv("CLIENTID", "opentdf-dpop")
    return sent


class TestRealmIssuesDPoPTokens:
    def test_a_bearer_realm_is_a_capability_gap(self, monkeypatch: pytest.MonkeyPatch):
        _token_endpoint(monkeypatch, "Bearer")
        with pytest.raises(pytest.skip.Exception) as excinfo:
            test_dpop._skip_unless_realm_issues_dpop_tokens()
        gap = tdfs.CapabilityGap.carried_by(excinfo.value)
        assert gap is not None, f"skip carries no capability gap: {excinfo.value!r}"
        assert gap == tdfs.CapabilityGap(
            subject="Keycloak client opentdf-dpop",
            feature="dpop",
            detail="Keycloak realm not configured for DPoP (token_type='Bearer'); "
            "set the realm's OAuth client to require DPoP-bound tokens",
        )
        assert excinfo.value.msg == gap.reason

    def test_a_dpop_realm_does_not_skip(self, monkeypatch: pytest.MonkeyPatch):
        sent = _token_endpoint(monkeypatch, "DPoP")
        test_dpop._skip_unless_realm_issues_dpop_tokens()
        assert len(sent) == 1

    def test_a_token_endpoint_nonce_challenge_is_retried(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        sent = _token_endpoint(monkeypatch, "DPoP", nonce_first=True)
        test_dpop._skip_unless_realm_issues_dpop_tokens()
        assert len(sent) == 2
