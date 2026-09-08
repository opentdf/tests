"""Per-provider OIDC configuration for the IdP conformance suite.

Each provider is a YAML file in idp/providers/. Secrets are never committed:
string fields may reference environment variables with `${VAR}` or
`${VAR:-default}` syntax; unresolved variables are collected so callers can
skip (PR runs) or fail (nightly `--idp-strict` runs) with a precise reason.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

PROVIDERS_DIR = Path(__file__).parent / "providers"

_ENV_REF = re.compile(r"\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}")


class Capabilities(BaseModel):
    """What the IdP supports.

    `dpop=None` means unknown: it is reported as a coverage gap (skip with
    reason), never as a pass or a fail.
    """

    dpop: bool | None = None
    # Can mint an access token for a different audience (negative-test input).
    custom_audience: bool = False
    # Token lifetime is configurable low enough to test real expiry.
    configurable_token_lifetime: bool = False


class ErsConfig(BaseModel):
    mode: Literal["keycloak", "claims", "multi-strategy"] = "claims"
    required_claims: list[str] = Field(default_factory=lambda: ["sub"])


class PlatformOverlay(BaseModel):
    dpop_enforce: bool = False
    # Extra policy lines (server.auth.policy.extension) — e.g. grant a group
    # from the provider's token claims a platform role. The platform accepts
    # the legacy `g, <group>, role:<role>` lines and, on builds that replaced
    # casbin with the grant table, translates them; the field name is kept
    # for compatibility with existing provider files.
    casbin_extension: str | None = None
    # Which token claim the platform reads group/role subjects from
    # (server.auth.policy.groups_claim; platform default realm_access.roles).
    # IdPs whose tokens carry no Keycloak-style roles need a claim that
    # exists, e.g. Auth0's gty or authnz-rs's arkavo_roles.
    casbin_groups_claim: str | None = None


class PlatformRequirement(BaseModel):
    """The platform build this IdP can front.

    The upstream platform accepts JWTs from any OIDC issuer, so most providers
    keep the default. A fork that only verifies another token format (e.g. the
    CWT-only arkavo-org fork) names itself here so a workflow can check out
    the right repository before rendering the overlay.
    """

    repo: str = "opentdf/platform"
    ref: str | None = None


class SubjectCondition(BaseModel):
    """How the test client shows up in the entity the platform resolves from
    this IdP's tokens, for the subject mappings the xtest fixtures create.

    Nothing about this is standard: Keycloak service-account tokens carry a
    `clientId` claim, a CWT identifies the client only through `sub`, another
    IdP may use `azp` or `client_id`. Declaring it per provider keeps the
    harness free of any one IdP's conventions. `selector` is the platform's
    subject-external-selector syntax (`.clientId`, `.sub`); `values` are the
    identities the shared subject condition set should match.
    """

    selector: str = ".clientId"
    values: list[str] = Field(
        default_factory=lambda: ["opentdf", "opentdf-sdk", "opentdf-dpop"]
    )


class ServiceSource(BaseModel):
    """Where a self-hosted IdP's source lives, for the workflow that builds it."""

    repo: str
    # Name of the workflow input that carries the ref to build.
    ref_input: str


class KnownIssue(BaseModel):
    """A check expected to fail for a known upstream reason.

    Applied as a non-strict xfail: the run stays green, the reason shows in
    reports, and an unexpected pass (XPASS) signals the upstream fix landed.
    """

    check: str
    reason: str
    issue: str | None = None


class IdpProvider(BaseModel):
    name: str
    display_name: str = ""
    # local: always available (Keycloak dev realm). external: needs secrets.
    # self-hosted: built from source and run inside the job (see `service`);
    # only workflows that know how to build it include the provider.
    tier: Literal["local", "external", "self-hosted"] = "external"
    # Bearer token format the IdP mints. Consumers (platform builds, SDKs)
    # that only handle one format use this to decide whether they can
    # participate; see `platform` and `sdks`.
    token_format: Literal["jwt", "cwt"] = "jwt"
    # Who re-ups the tenant credentials when they expire.
    owner: str = ""
    # False while the tenant/secrets don't exist yet: the provider never gates
    # a run (skips with a pointer to its setup runbook, even --idp-strict) and
    # the nightly matrix excludes it. Flip to true once the tenant is live.
    onboarded: bool = True
    issuer: str
    audience: str
    client_id: str
    client_secret: str
    # Token endpoint, for CLIs that take it from the environment instead of
    # discovering it from the platform well-known (opentdf-rs's xtest_cli).
    # Leave unset to rely on discovery.
    token_endpoint: str | None = None
    # Some IdPs bind DPoP per-client (Keycloak); most use the same client.
    dpop_client_id: str | None = None
    dpop_client_secret: str | None = None
    # Extra form fields for the token request (e.g. Auth0's `audience`).
    token_endpoint_params: dict[str, str] = Field(default_factory=dict)
    # Audience value to request for the wrong-audience negative test.
    wrong_audience: str | None = None
    # A real access token that has since expired (safe to commit: it's
    # expired). Enables the expired-token negative test without needing a
    # short-lifetime client.
    expired_token: str | None = None
    capabilities: Capabilities = Field(default_factory=Capabilities)
    ers: ErsConfig = Field(default_factory=ErsConfig)
    platform_overlay: PlatformOverlay = Field(default_factory=PlatformOverlay)
    platform: PlatformRequirement = Field(default_factory=PlatformRequirement)
    # SDKs able to use this IdP's tokens; empty means no restriction.
    sdks: list[str] = Field(default_factory=list)
    subject_condition: SubjectCondition = Field(default_factory=SubjectCondition)
    service: ServiceSource | None = None
    known_issues: list[KnownIssue] = Field(default_factory=list)

    def dpop_credentials(self) -> tuple[str, str]:
        return (
            self.dpop_client_id or self.client_id,
            self.dpop_client_secret or self.client_secret,
        )


@dataclass
class ResolvedProvider:
    provider: IdpProvider
    missing_secrets: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.missing_secrets


def _interpolate(value: Any, missing: list[str]) -> Any:
    if isinstance(value, str):

        def repl(match: re.Match[str]) -> str:
            var, default = match.group(1), match.group(2)
            env = os.environ.get(var)
            if env:
                return env
            if default is not None:
                return default
            if var not in missing:
                missing.append(var)
            return ""

        return _ENV_REF.sub(repl, value)
    if isinstance(value, dict):
        return {k: _interpolate(v, missing) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v, missing) for v in value]
    return value


def list_providers() -> list[str]:
    return sorted(p.stem for p in PROVIDERS_DIR.glob("*.yaml"))


def load_provider(name: str) -> ResolvedProvider:
    path = PROVIDERS_DIR / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(
            f"no IdP provider config for {name!r} at {path} "
            f"(available: {', '.join(list_providers())})"
        )
    raw = yaml.safe_load(path.read_text())
    missing: list[str] = []
    data = _interpolate(raw, missing)
    return ResolvedProvider(
        provider=IdpProvider.model_validate(data), missing_secrets=missing
    )
