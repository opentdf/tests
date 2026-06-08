# Keycloak 26 DPoP & Security Enforcement Reference Notes

Keycloak v26 promotes **DPoP (OAuth 2.0 Demonstrating Proof-of-Possession at the Application Layer, RFC 9449)** from a preview feature to **fully supported (v26.4.0)** and encourages its enforcement across OAuth clients. This change is aimed at mitigating token replay attacks by ensuring that standard Bearer tokens can no longer be used if intercepted without the associated private cryptographic key.

---

## 1. Key DPoP Features & Enforcement in Keycloak v26

### 1.1 Promotion to Full Support (v26.4.0)
- **Production-Ready:** DPoP is no longer an experimental or "preview" feature. It is officially supported and integrated into the core security profiles.
- **Ecosystem Adoption:** Because DPoP is fully supported, Keycloak-based enterprise setups (e.g., in OpenTDF deployment environments) can now globally mandate DPoP. Under high-security profiles, standard Bearer tokens are rejected outright, breaking clients that have not upgraded to support DPoP.

### 1.2 Expanded Grant Type Support
- DPoP support is now extended beyond the standard `authorization_code` flow to **all OAuth 2.0 grant types** supported by Keycloak, including:
  - `client_credentials` (the primary flow used by machine-to-machine integrations like the OpenTDF Email Gateway)
  - `refresh_token`
  - `authorization_code`
  - `urn:ietf:params:oauth:grant-type:token-exchange` (Token Exchange)

### 1.3 UserInfo and Endpoints Support
- The `/protocol/openid-connect/userinfo` endpoint has been upgraded to support DPoP-bound tokens.
- All Keycloak-internal endpoints (such as token revocation, token introspection, and user info) accept DPoP-bound tokens and validate DPoP proofs.

### 1.4 Pushed Authorization Requests (PAR) & Authorization Code Binding
- Keycloak 26 supports binding the authorization code itself to a DPoP key during Pushed Authorization Requests (PAR), preventing code-injection/interception attacks.

### 1.5 FAPI 2.0 Security Profiles
- Keycloak v26 introduces formal client profiles:
  - `fapi-2-dpop-security-profile`
  - `fapi-2-dpop-message-signing`
- These profiles make DPoP mandatory for client communication, aligning with the Financial-grade API (FAPI) 2.0 security specifications.

---

## 2. Admin Console & Client Configuration

Administrators can enforce DPoP on a per-client or realm-wide basis.

### 2.1 Enforcing DPoP on a Client
1. Navigate to **Clients** in the Keycloak Admin Console.
2. Select the target client (e.g., `dsp-email-gateway`).
3. Scroll to **Advanced Settings**.
4. Locate the configuration: **"Require DPoP bound tokens"** (key: `dpop.bound.access.tokens`).
5. When turned **ON** (`true`):
   - Keycloak will **reject** any token request from this client that lacks a valid `DPoP` header containing a DPoP proof.
   - Any access tokens issued to this client will be bound to the public key supplied in the proof.
   - Keycloak will only accept that access token at its own endpoints (like UserInfo) if accompanied by a corresponding DPoP proof.

### 2.2 Workarounds & Deprecations
- **The Workaround (AB-2235):** Disabling DPoP binding on the client via `dpop.bound.access.tokens = "false"` allows legacy clients to connect using standard Bearer tokens. This introduces a security gap, as it defeats sender-constraint protections.
- **Goal:** Enable `dpop.bound.access.tokens = "true"` and have the SDK/client automatically generate DPoP proof JWTs to authenticate securely.

---

## 3. Impact on OpenTDF Components

- **Java SDK:** The Java SDK must be enhanced to support generating DPoP proofs during token requests (`POST /token`) and subsequent API resource requests (e.g., interacting with KAS or Platform services).
- **Platform (KAS & Services):** The OpenTDF Platform's internal services, specifically KAS, must be able to:
  1. Detect when Keycloak returns a `DPoP` token type (indicated by `token_type: "DPoP"` in the token response).
  2. Handle authentication headers prefixed with `DPoP ` instead of `Bearer `.
  3. Validate the `DPoP` proof header sent alongside the token, verifying the `jkt` (JWK Thumbprint) contained in the access token's `cnf` claim matches the public key that signed the DPoP proof.
- **Web SDK & Others:** Must maintain parity with DPoP requirements to support deployment under FAPI 2.0 / Keycloak 26 environments.
