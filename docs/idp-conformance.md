# Black-Box IdP Conformance

Provider-agnostic checks that exercise the platform's auth surface against any
OIDC provider described by a config in `xtest/idp/providers/`. Origin:
[GitHub discussion opentdf#3327](https://github.com/orgs/opentdf/discussions/3327).

The suite (`xtest/test_idp_conformance.py`) is black-box: it talks to the
provider's discovery document, JWKS, and token endpoint, and to the platform's
public endpoints, exactly the way an SDK would. Each check is a pass/fail/skip
with a short reason, so the junit output doubles as a compatibility matrix.

**Key architecture fact:** SDKs read `platform_issuer` from the platform
well-known (`/.well-known/opentdf-configuration`) and OIDC-discover the token
endpoint from it, so re-pointing the platform at an IdP automatically
re-points every SDK — no SDK-side IdP config is needed. The platform validates
the issuer string exactly (the discovered issuer wins over the configured
one), which is why the provider configs warn about trailing slashes.

**Non-goals:**

- The Keycloak CI path stays the default everywhere else; this suite adds a
  lane, it does not re-point existing xtest workflows.
- Provider admin APIs are not tested — the suite only exercises the
  token-consumer side (what the platform and SDKs see).
- No secrets in the repo. Secrets arrive as `IDP_<PROVIDER>_*` environment
  variables (GitHub Actions secrets in CI); provider YAMLs only reference them.

## Running locally

### Keycloak (default, no secrets needed)

The local Keycloak dev realm doubles as the suite's self-check against a
known-good IdP:

```bash
cd otdf-local && uv run otdf-local up
eval $(uv run otdf-local env)
cd ../xtest
uv run pytest test_idp_conformance.py -v
```

### External provider (e.g. Auth0)

1. Complete the one-time tenant setup (`docs/idp-setup/<provider>.md`) and
   export the secrets, e.g. `IDP_AUTH0_CLIENT_ID` / `IDP_AUTH0_CLIENT_SECRET`.
2. Render a platform config that trusts the provider and restart the platform
   with it:

   ```bash
   cd xtest
   uv run python -m idp.platform_config auth0 \
     --base ../platform/opentdf-dev.yaml --out ../platform/opentdf.yaml
   # restart the platform with the rendered config
   ```

   The overlay patches `server.auth.issuer` / `server.auth.audience`,
   `server.auth.dpop.enforce`, `server.auth.policy.{groups_claim,extension}`
   and `services.entityresolution.mode` from the provider YAML.
   `--fragment out.yaml` writes only those keys (merge with
   `yq -i '. *= load("out.yaml")' opentdf.yaml`), and `--env` prints the
   `export` lines the harness and SDK CLIs need for the provider
   (`CLIENTID`, `CLIENTSECRET`, `TOKENENDPOINT` when declared,
   `XT_SUBJECT_SELECTOR` / `XT_SUBJECT_VALUES`).
   `uv run python -m idp.platform_config --help` for usage.
3. Run the suite against that provider:

   ```bash
   uv run pytest test_idp_conformance.py --idp-providers auth0 -v
   # or several at once:
   uv run pytest test_idp_conformance.py --idp-providers "keycloak auth0" -v
   ```

The `idp` fixture **skips** a provider when its secrets are missing, or when
the running platform's well-known `platform_issuer` does not match the
provider's issuer (i.e. you forgot step 2). Pass `--idp-strict` to turn both
skips into failures — this is what the nightly CI uses.

## Provider configs (`xtest/idp/providers/*.yaml`)

Each provider is one YAML file, validated by the pydantic schema in
`xtest/idp/provider.py`. String fields support `${VAR}` and `${VAR:-default}`
interpolation; unresolved variables are collected as **missing secrets**,
which skip the provider (or fail it under `--idp-strict`).

| Field | Purpose |
|-------|---------|
| `name` | Provider key — must match the file name (`<name>.yaml`). |
| `display_name` | Human label for reports. |
| `tier` | `local` (always available, e.g. Keycloak dev realm), `external` (needs secrets), or `self-hosted` (built from source and run inside the job; only workflows that know how to build it include it, see `service`). PRs run local only. |
| `token_format` | `jwt` (default) or `cwt`. Platform builds and SDKs that handle only one format use it to decide whether they can participate. |
| `platform.repo` / `platform.ref` | The platform build this IdP can front (default `opentdf/platform`). The CWT-only arkavo-org fork names itself here. |
| `sdks` | SDKs able to use this IdP's tokens; empty means no restriction. |
| `service.repo` / `service.ref_input` | For `self-hosted` providers: source repository and the workflow input carrying the ref to build. |
| `token_endpoint` | Only for CLIs that read `TOKENENDPOINT` from the environment instead of discovering it (opentdf-rs's `xtest_cli`). Leave unset to rely on discovery. |
| `subject_condition.selector` / `subject_condition.values` | How the test client appears in the entity the platform resolves from this IdP's tokens, for the subject mappings the attribute fixtures create. Keycloak: `.clientId` in `[opentdf, opentdf-sdk, opentdf-dpop]` (the default). A CWT from authnz-rs: `.sub` in `[client:opentdf]`. Exported to the harness as `XT_SUBJECT_SELECTOR` / `XT_SUBJECT_VALUES` by `--env`. |
| `owner` | Who re-ups the tenant credentials when they expire. |
| `onboarded` | `false` while the tenant/secrets don't exist yet: the provider never gates a run (skips with a pointer to its runbook, even `--idp-strict`) and the nightly matrix excludes it. Flip to `true` once the tenant is live. |
| `issuer` | OIDC issuer URL. Compared **exactly** against the discovery document and the platform config — keep trailing slashes as the IdP emits them. |
| `audience` | The value the platform expects in the token's `aud` claim. |
| `client_id` / `client_secret` | Client-credentials grant client. Usually `${IDP_<NAME>_CLIENT_ID}` / `${IDP_<NAME>_CLIENT_SECRET}`. |
| `dpop_client_id` / `dpop_client_secret` | Optional separate DPoP-bound client (Keycloak binds DPoP per-client; most IdPs use the same client). |
| `token_endpoint_params` | Extra form fields for the token request (e.g. Auth0's `audience`, Entra's `scope`). |
| `wrong_audience` | Audience value to request for the wrong-audience negative test. Required when `capabilities.custom_audience` is true. |
| `expired_token` | A real access token that has since expired. Safe to commit (it's expired); enables the expired-token negative test. |
| `capabilities.dpop` | `true` / `false` / **null = unknown** — unknown is reported as a coverage gap (skip with reason), never as pass or fail. |
| `capabilities.custom_audience` | Can the IdP mint an access token for a different audience (negative-test input)? |
| `capabilities.configurable_token_lifetime` | Is token lifetime configurable low enough to test real expiry? |
| `ers.mode` | `keycloak` \| `claims` \| `multi-strategy` — rendered into the platform overlay. |
| `ers.required_claims` | Claims the ERS mode needs from the token (default `[sub]`). |
| `platform_overlay.dpop_enforce` | Rendered into `server.auth.dpop.enforce` in the overlay. |
| `platform_overlay.casbin_extension` | Extra casbin policy lines appended to the builtin policy (`server.auth.policy.extension`) — e.g. grant a token claim value the platform admin role. |
| `platform_overlay.casbin_groups_claim` | Which token claim casbin reads group/role subjects from (`server.auth.policy.groups_claim`; platform default `realm_access.roles`). Auth0 uses `gty` (always `client-credentials` for M2M tokens) since its tokens carry no roles claim. |
| `known_issues` | List of `{check, reason, issue}` — applied as non-strict xfail for documented upstream bugs (run stays green, reason shows in reports, an unexpected pass flags the fix landing). See auth0's `tdf_roundtrip` entry for the shape. |

### Adding a new provider

1. Copy the closest template in `xtest/idp/providers/` and fill in `issuer`
   and `audience` (watch exact-string issuer matching — trailing slashes
   matter).
2. Reference secrets as `${IDP_<NAME>_*}`; never commit real values.
3. Mark `capabilities` honestly — leave `dpop` null (unknown) until a first
   run against the real tenant proves it either way.
4. Write the one-time tenant setup steps as `docs/idp-setup/<name>.md`.
5. Add the secrets to GitHub Actions as `IDP_<NAME>_*` (the workflow already
   passes the standard ones through; extend the env block in
   `.github/workflows/idp-conformance.yml` for new variable names).
6. Assign an `owner` — see Credential ownership below.
7. Once the tenant is live and a manual run passes, set `onboarded: true` —
   the provider joins the nightly matrix and starts gating scheduled runs.

## The checks

| Check | What it proves | Gating |
|-------|----------------|--------|
| `discovery_document` | Provider discovery doc is reachable and well-formed; its issuer matches the configured issuer exactly; `client_credentials` is advertised. | — |
| `jwks_fetch` | Provider JWKS is reachable and every key has `kty` + `kid`. | — |
| `client_credentials_token` | Client-credentials grant mints a token whose `iss` matches discovery, whose `aud` contains the platform audience, that is unexpired and carries a `sub`. | — |
| `platform_accepts_provider_token` | The platform accepts this provider's token on a protected endpoint (200, or 403 if casbin denies — authN is what is being proven, authZ is a separate surface). | — |
| `ers_resolves_entity` | ERS resolves the provider token into an entity chain; in `claims` mode the response reflects the token's `sub`. | — |
| `dpop_proof_of_possession` | DPoP-bound token (`cnf.jkt`) plus proof round-trip against the platform, including the nonce-challenge retry. | `capabilities.dpop` (null → skip, reported as gap) + platform `dpop` feature |
| `wrong_audience_rejected` | A token minted for `wrong_audience` is rejected with 401. | `capabilities.custom_audience` |
| `tampered_signature_rejected` | A token with an altered signature is rejected with 401. | — |
| `unknown_signer_rejected` | A well-formed JWT signed by an unknown key is rejected with 401; also exercises the platform's JWKS refetch-on-unknown-kid (rotation) path. | — |
| `expired_token_rejected` | A committed expired token is rejected with 401. | needs `expired_token` in the provider config |
| `tdf_roundtrip` | Full encrypt → KAS rewrap → decrypt under this IdP, using an attribute-free TDF (no entitlement provisioning needed). Runs through the first available SDK CLI — prefers `go` dist/main, then any installed `go`/`java`/`js` version. | needs an SDK CLI installed |

## CI (`.github/workflows/idp-conformance.yml`)

- **Pull requests** (path-filtered to the suite): keycloak tier only — no
  secrets are available on PRs, and the local tier validates the suite itself.
- **Nightly** (`17 7 * * *`): the local tier plus every **onboarded** external
  provider, run with `--idp-strict`. Non-onboarded templates are excluded at
  matrix-resolution time so an un-donated tenant never fails the run. On
  failure the workflow opens or updates a GitHub issue labeled
  `idp-conformance`. A nightly failure is often "the provider changed
  something" or an expired tenant secret — it pages the provider owner instead
  of wedging main.
- **`workflow_dispatch` / `workflow_call`**: `providers` ("all" or
  space-separated names), `platform-ref`, and `otdfctl-ref` inputs.
- **Publishing**: the Community Conformance Pages workflow
  (`community-pages.yml`) rebuilds on IdP Conformance completion and folds the
  latest run's `idp-conformance-results-*` artifacts into the site — the IdP
  matrix renders alongside the SDK matrices.

External-tier jobs do **not** use the Keycloak-bundled startup action. They
check out `opentdf/platform`, start only Postgres from its docker-compose,
render the provider overlay onto `opentdf-dev.yaml`, build and start the
platform, provision fixtures (non-fatal — the attribute-free roundtrip does
not depend on them), and run the suite.

### Platform-repo follow-up (recommended)

The platform repo should call this workflow on PRs that touch its auth
surface, via `workflow_call`, path-filtered to:

```
service/internal/auth/**
service/pkg/auth/**
service/entityresolution/**
service/kas/**
service/wellknownconfiguration/**
sdk/auth/**
protocol/go/**
```

Note: the discussion's original filter list missed `service/internal/auth/**`,
which is where the auth middleware actually lives — include it.

## Credential ownership & rotation

Every external provider config has an `owner` — the person or team that re-ups
the tenant credentials when they expire. The nightly run doubles as expiry
detection: a token-acquisition failure (`client_credentials_token`) fails the
run under `--idp-strict` and files the `idp-conformance` issue, which should
route to the owner listed in `xtest/idp/providers/<name>.yaml`. Rotation
procedure per provider lives in `docs/idp-setup/<name>.md`.

## Known degradations

- **Expired-token and key-rotation negatives can't be forced on public IdPs.**
  You cannot ask Auth0 to mint an already-expired token or to rotate a key on
  demand. Instead: mint a token, let it expire, and commit it as
  `expired_token` (safe — it's expired); rotation coverage comes from
  `unknown_signer_rejected`, which exercises the platform's JWKS
  refetch-on-unknown-kid path.
- **ERS `multi-strategy` mode is a v2-only preview**, so it is folded into the
  provider config (`ers.mode`) rather than made a CI matrix axis. Providers
  default to `claims`; Keycloak uses its native `keycloak` mode.

## Layout

| Path | Contents |
|------|----------|
| `xtest/test_idp_conformance.py` | The checks. |
| `xtest/idp/provider.py` | Pydantic schema + `${VAR}` interpolation for provider configs. |
| `xtest/idp/providers/*.yaml` | Per-provider configs (`keycloak` + external templates). |
| `xtest/idp/oidc.py` | Minimal discovery / JWKS / client-credentials client (hand-rolled on `requests`). |
| `xtest/idp/dpop.py` | DPoP machinery, shared with `test_dpop.py`. |
| `xtest/idp/platform_config.py` | Renders a platform YAML overlay for a provider (`uv run python -m idp.platform_config`). |
| `xtest/fixtures/idp.py` | `--idp-providers` / `--idp-strict` options and the session-scoped `idp` fixture. |
| `docs/idp-setup/*.md` | One-time tenant setup runbooks per provider. |
