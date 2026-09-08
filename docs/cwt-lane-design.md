# CWT lane: fork platform + authnz-rs with the CWT SDKs — design

Date: 2026-09-07. Status: design for review; supersedes the earlier draft that
put an `arkavo-main` lane in the go/java/js matrix (dropped: those SDKs are not
CWT SDKs, so that lane could never pass).

## Goal

Test the `arkavo-org/opentdf-platform` fork, which only accepts **CWT** bearer
tokens, with **authnz-rs** as its identity provider and the SDKs that speak
CWT (**opentdf-rs** and **OpenTDFKit**), as a lane in the community matrix.

The IdP is modelled as a provider config next to Keycloak and Auth0 (both JWT)
so that "IdP / token format" is a matrix dimension the future superset matrix
(official + community SDKs) can reuse. That superset matrix is out of scope
here; this design only makes sure nothing done now works against it.

First milestone: a smoke lane — the fork boots against authnz-rs and
`test_tdfs.py::test_tdf_roundtrip` passes for rust and swift in both
directions (`rust→rust`, `rust→swift`, `swift→rust`, `swift→swift`) with the
Base TDF container.

Out of scope: ABAC, PQC, multi-KAS, audit-log assertions, DPoP-bound (`cnf`)
tokens, python (no CWT support), go/java/js against the fork, and CWT
black-box checks in the IdP conformance suite (a natural follow-up that reuses
the same provider YAML).

## Facts this design rests on

- The fork removed inbound JWT verification (`15f5cf46`). At boot it fetches
  the issuer's OIDC discovery document and fails unless it advertises
  `cose_keys_uri`. Auth cannot be disabled as a workaround: KAS rewrap reads
  the access token from the request context.
- Local spike (2026-09-07): authnz-rs (`7d2bf69`, Rust 1.95 MSRV) starts with
  three P-256 PEMs (`SIGN_KEY_PATH` SEC1, `ENCODING_KEY_PATH` PKCS8,
  `DECODING_KEY_PATH` public), an `apple-app-site-association.json` in its
  working directory, `OIDC_ISSUER`, `OIDC_PLATFORM_AUDIENCE`, one
  `OIDC_CLIENT_<TAG>_{ID,SECRET,REDIRECT_URIS}` triple and dummy `AWS_*` vars.
  DynamoDB is lazy; Redis failure is logged, not fatal. Discovery advertises
  `cose_keys_uri`; `client_credentials` mints a CWT with `sub = client:<id>`,
  `aud = [<client_id>, <platform audience>]`, `arkavo_roles =
  [service-account]`, `arkavo_entitlements = [tdf:create, tdf:decrypt]`.
  authnz-rs ignores DPoP proofs, so tokens carry no `cnf` (fine while
  `server.auth.enforceDPoP: false`).
- CWT-capable SDKs: opentdf-rs (`kas.rs`: opaque JWT-or-CWT passthrough,
  `kas_discovery.rs` parses `cose_keys_uri`) and OpenTDFKit
  (`KASRewrapClient.swift`, `KASDiscovery.swift`). opentdf-python-sdk has no
  CWT support. Swift builds only on macOS.
- The community workflow already has a macOS stage-2 job
  (`community-stage2-swift-peers`) that builds python, rust and swift CLIs,
  starts the platform through this repo's own
  `.github/actions/start-up-with-containers-macos` (native Postgres and
  Keycloak, no Docker), and runs `test_tdfs.py -m stage1 --containers tdf`.
- The IdP provider abstraction exists: `xtest/idp/providers/*.yaml`
  (pydantic schema in `xtest/idp/provider.py`) and `idp.platform_config`,
  which renders a platform config overlay setting `server.auth.issuer`,
  `audience`, `dpop.enforce`, `policy.groups_claim`, `policy.extension` and
  `services.entityresolution.mode`. Auth0 already uses `ers.mode: claims` with
  `casbin_groups_claim: gty` and an extension granting `role:admin`; the fork
  needs the same shape with `arkavo_roles` / `service-account`.
- The fork's claims-mode entity resolution exposes the token's private claims
  (plus `sub`, `iss`, `jti`, `aud`) as the entity. xtest's shared subject
  condition set (`fixtures/obligations.py::otdf_client_scs`) selects
  `.clientId IN [opentdf, opentdf-sdk, opentdf-dpop]`; authnz-rs CWTs carry
  no `clientId` today.
- Policy administration in `test_tdf_roundtrip` fixtures runs through otdfctl
  (go, from the upstream platform), which authenticates with the same
  `opentdf`/`secret` client. The fork's casbin policy needs `role:admin` for
  writes; `role:unknown` may already rewrap.
- Token endpoint discovery: OpenTDFKitCLI takes `CLIENTID`/`CLIENTSECRET`/
  `PLATFORMURL` and discovers the IdP from the platform well-known;
  opentdf-rs `xtest_cli` reads `TOKENENDPOINT` (fallback `KCFULLURL`) from the
  environment, so the lane must export `TOKENENDPOINT`.
- The fork reports service version 0.15.0. xtest gates `key_management`,
  `ecwrap`, `obligations` and `audit_logging` on by version. PQC must stay
  off (the macOS action's `pqc-enabled` input).
- The IdP conformance workflow builds its matrix by grepping `tier:` from
  every provider YAML and only knows `local` and `external`; a new provider
  with another tier must be filtered out there.

## Decisions

| Decision | Choice | Alternative considered |
|---|---|---|
| Lane home | New macOS job in `community-xtest.yml` next to stage-2 | authnz-rs as a provider in `idp-conformance.yml` (Ubuntu, rust only, needs CWT variants of the black-box checks) |
| SDKs | rust and swift, both directions | Include python (no CWT), go/java/js (not CWT SDKs) |
| IdP config | `xtest/idp/providers/authnz-rs.yaml` + `idp.platform_config` overlay | Ad-hoc yq in the workflow |
| IdP delivery | Build authnz-rs from source in the job (cargo, rust-cache) | Container image published from authnz-rs CI |
| Entitlement | authnz-rs adds a `clientId` claim to client_credentials CWTs | Attribute-free (ecwrap-only) roundtrip |
| go/java/js vs fork | Removed from `xtest.yml` (PR #11 reduced to the go build-gate fix) | Non-blocking lane |

## Architecture

```
community-xtest.yml
  resolve-refs ─── adds: authnz-ref, fork-platform-ref (defaults: main)
       │
       ├─ (existing) python/rust/swift stage-1 and stage-2 jobs — unchanged
       │
       └─ cwt-rust-swift  (macos-latest)              "rust × swift @ authnz-rs (CWT)"
            1. checkout tests; setup-xcode; uv + python; go; rust toolchain
            2. checkout arkavo-org/authnz-rs @ authnz-ref; cargo build --release
            3. start authnz-rs :8899 (keys, site-association file, env)
            4. render provider overlay fragment:  idp.platform_config authnz-rs --fragment
            5. start-up-with-containers-macos
                 platform-repo: arkavo-org/opentdf-platform, platform-ref: fork-platform-ref
                 idp: external  (skip Keycloak install/start/provision, skip test.env alignment)
                 config-overlay-file: <fragment>   (merged into opentdf.yaml before start)
                 pqc-enabled: false
            6. otdfctl (go@latest) for policy admin; build rust + swift CLIs
            7. pytest -m stage1 --containers tdf
                 --sdks-encrypt "rust@main swift@main" --sdks-decrypt "rust@main swift@main"
                 --focus "rust swift" --no-audit-logs
                 env: TOKENENDPOINT=http://localhost:8899/oauth/token
                      KCFULLURL=http://localhost:8899  (issuer, for anything reading it)
            8. upload results + authnz-rs.log + platform log
```

Token flow: CLI → `client_credentials` at authnz-rs (`opentdf`/`secret`) →
CWT → Bearer to platform/KAS → fork `CWTVerifier` validates against
`/.well-known/cose-keys` → claims-mode ERS exposes `clientId` → subject
mapping matches → rewrap allowed. otdfctl follows the same path for policy
writes and is authorised through `arkavo_roles: [service-account]` →
`role:admin` (test-only mapping).

## Changes

### 1. authnz-rs (PR in arkavo-org/authnz-rs)

Add `client_id: Option<String>` to `CustomClaims` (`src/cwt.rs`), emitted as
the text-label claim `clientId`, set in `handle_client_credentials_grant`
(`src/oidc.rs`) to the authenticated `client_id`; add the same claim to the
`id_token`. Keycloak service-account tokens carry `clientId`, which is why
xtest's subject condition set selects it. Unit test: a client_credentials
mint yields `clientId == client_id`.

### 2. Provider config: `xtest/idp/providers/authnz-rs.yaml`

Schema additions in `xtest/idp/provider.py` (all optional, defaults keep
existing providers valid):

- `tier: "self-hosted"` — a third tier: the IdP is built and run inside the
  job. `idp-conformance.yml`'s matrix step skips tiers it does not handle.
- `token_format: Literal["jwt", "cwt"] = "jwt"`.
- `platform: {repo: str = "opentdf/platform", ref: str | None = None}` — the
  platform this IdP requires (the fork, for authnz-rs).
- `sdks: list[str] = []` — SDKs able to use this token format; empty means
  "no restriction". Selection stays explicit here; a runtime `supports cwt`
  probe in the CLI contract is a follow-up once the SDK repos expose it.
- `service: {repo, ref_input}` — where the self-hosted IdP's source lives and
  which workflow input names its ref (documentation for the workflow; the
  build recipe itself lives in the workflow).

Provider values: issuer `http://localhost:8899`, audience
`http://localhost:8080`, client `opentdf`/`secret`, `ers.mode: claims`,
overlay `dpop_enforce: false`, `casbin_groups_claim: arkavo_roles`,
`casbin_extension: "g, service-account, role:admin"`, `capabilities.dpop:
false`, `sdks: [rust, swift]`, `known_issues: []`.

`idp.platform_config` gains `--fragment`, writing only the overlay keys as a
YAML fragment that a config step can merge with
`yq -i '. *= load("fragment.yaml")' opentdf.yaml`. The existing `--base/--out`
mode is unchanged.

### 3. macOS action inputs (`.github/actions/start-up-with-containers-macos`)

- `platform-repo` (default `opentdf/platform`) used by the checkout step,
  validated as `owner/name`.
- `idp` (`keycloak` default | `external`): when `external`, skip "Install
  OpenJDK", "Download and start Keycloak", "Provision Keycloak realm /
  clients" and "Align test.env IdP host". Keytool is only needed for
  Keycloak's truststore, so OpenJDK is skipped too.
- `config-overlay-file` (default empty): merged into `opentdf.yaml` after
  "Map config keys + enable Stage-1 options" and before the platform starts.
  Merge is `yq -i '. *= load(strenv(OVERLAY))'`; the step is skipped when
  empty and fails the job on a yq error.

Existing callers pass none of these and behave exactly as today.

### 4. `community-xtest.yml`

- Inputs `authnz-ref` and `fork-platform-ref` (default `main`) on
  `workflow_dispatch`; `resolve-refs` resolves both to SHAs
  (`resolve_or_pass` for authnz-rs against `arkavo-org/authnz-rs`; GitHub API
  for `arkavo-org/opentdf-platform`) and adds them to the summary table.
- New job `community-cwt-rust-swift` ("rust × swift @ authnz-rs (CWT)"),
  `macos-latest`, `timeout-minutes: 120`, gated like stage-2 by the
  `stage` input (treated as stage 2). Steps as in the architecture sketch.
  authnz-rs build uses `dtolnay/rust-toolchain@stable` (already used) plus
  pinned `Swatinem/rust-cache`; start via `JarvusInnovations/background-action`
  waiting on `http://localhost:8899/.well-known/openid-configuration`, log to
  `authnz/authnz-rs.log`.
- The capstone `community-xtest` job adds the new job to its required set
  with the same skipped-when-stage-filtered rule.
- Because the fork validates discovery at boot, authnz-rs must be healthy
  before the macOS action runs.

### 5. `idp-conformance.yml`

The "Compute provider matrix" step only includes `local` and `external`
tiers and logs the skip for others, so `authnz-rs.yaml` does not enter that
matrix until CWT checks exist.

### 6. `xtest.yml` / PR #11

PR #11 is reduced to the go build-gate fix (build when a released otdfctl
falls back to source). The vendored Ubuntu action, `arkavo-main` lane and
fork plumbing are removed.

### 7. Docs

README community table gains the CWT lane row; `docs/community-conformance.md`
gets a short "CWT lane" section pointing here; project memory updated.

## Failure semantics

- The CWT job is a required job in the community capstone (hard-fail),
  consistent with the other community lanes.
- authnz-rs build or start failure fails the job at that step; platform boot
  failure surfaces in the macOS action with the platform log; both logs are
  uploaded on failure.
- Test failures are reported by SDK pair and test name. SDK-side fixes
  (rust/swift) are separate PRs in their repos; the lane is not softened.

## Verification

1. authnz-rs PR: unit test for `clientId`; local spike re-run shows the claim
   in the decoded CWT.
2. Provider schema: `uv run pytest test_self.py` plus ruff/pyright in `xtest`;
   `uv run python -m idp.platform_config authnz-rs --fragment` renders the
   expected keys; `keycloak`/`auth0` renders are byte-identical to before.
3. Workflow dry run: `workflow_dispatch` with `stage: 2` on the branch. Early
   signals: authnz-rs discovery reachable; platform boots without the
   `cose_keys_uri` error; `Platform version` step prints 0.15.0; otdfctl
   policy fixtures succeed (admin mapping works); pytest collects 4 pairs.
4. Existing stage-1/stage-2 jobs and the IdP conformance workflow stay green.

## Risks

- Java-free but otdfctl-dependent: policy admin through `otdfctl@latest`
  against a 0.15-era API (`kas-registry key create`, subject mappings) may
  drift. Reported, not patched here.
- opentdf-rs `xtest_cli` and OpenTDFKitCLI have not yet fetched a token from
  authnz-rs in CI; the Go SDK path was spiked, theirs was read from source.
- macOS runner minutes: one more ~60–90 min macOS job per run (authnz-rs
  cold build ~10 min on the runner, cached after).
- `tier: self-hosted` is new; anything else grepping tiers must be checked
  (only `idp-conformance.yml` does today).
