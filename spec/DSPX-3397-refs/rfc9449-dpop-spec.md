# RFC 9449 - OAuth 2.0 Demonstrating Proof-of-Possession (DPoP) Technical Reference

**OAuth 2.0 Demonstrating Proof-of-Possession at the Application Layer (DPoP)** is an IETF standard (RFC 9449) designed to prevent token reuse and replay attacks. DPoP ensures that access and refresh tokens are sender-constrained, meaning they can only be used by the client that holds the private cryptographic key associated with the token.

---

## 1. DPoP Proof JWT Structure

A **DPoP Proof** is a short-lived JSON Web Token (JWT) sent by the client in the `DPoP` HTTP header. It is signed by an asymmetric private key belonging to the client. The public key is embedded directly in the JWT's header.

### 1.1 JWT Header
The header of a DPoP Proof JWT must contain:
- `typ`: Must be exactly `"dpop+jwt"`.
- `alg`: The digital signature algorithm (e.g., `ES256`, `RS256`, `PS256`, `EdDSA`).
- `jwk`: The public key corresponding to the private key used to sign the JWT, formatted as a JSON Web Key (JWK). Must **not** contain any private key parameters.

*Example Header:*
```json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "f83OJ3D2xF1Bg8vub9t61_Vn_M8v6j8v6j8v6j8v6j8",
    "y": "x_da4Nf_y_V6m289J1Q33835K0q_FAbD2W6fGv6b8sY"
  }
}
```

### 1.2 JWT Payload
The payload contains claims that bind the proof to the specific HTTP request, preventing replay:
- `jti`: A unique identifier for the JWT. Used to prevent replay attacks within a short time window.
- `htm`: The HTTP method of the request (e.g., `"GET"`, `"POST"`, `"PUT"`), in uppercase.
- `htu`: The HTTP target URI of the request, without query or fragment components (e.g., `"https://as.example.com/token"`).
- `iat`: The time at which the JWT was issued (Unix epoch timestamp).
- `ath`: **Required** when making resource requests. It is the Base64url-encoded SHA-256 hash of the ASCII representation of the access token. (Must **not** be included when requesting a new token, as no token exists yet).
- `nonce`: **Required if provided by the server.** An opaque string supplied by the authorization server or resource server in a `DPoP-Nonce` HTTP response header.

*Example Payload (Token Request - no access token yet):*
```json
{
  "jti": "g3bZ9-8A1b2c",
  "htm": "POST",
  "htu": "https://as.example.com/protocol/openid-connect/token",
  "iat": 1780000000
}
```

*Example Payload (Resource Request - with access token):*
```json
{
  "jti": "v9X8-1a2b3c4d",
  "htm": "GET",
  "htu": "https://api.example.com/kas/v2/keys",
  "iat": 1780000100,
  "ath": "fU_S9_8Z9_8Z9_8Z9_8Z9_8Z9_8Z9_8Z9_8Z9_8Z9_8"
}
```

---

## 2. Core Protocol Flows

### 2.1 Flow A: Requesting an Access Token (e.g., Client Credentials)
1. **Client Key Pair Generation:** The client generates or retrieves an asymmetric key pair (e.g., EC P-256 or RSA 2048).
2. **Client DPoP Proof Generation:** The client creates a DPoP Proof JWT.
   - Header: Contains `typ: "dpop+jwt"`, the signature algorithm, and the public key `jwk`.
   - Payload: Contains `jti`, `htm: "POST"`, `htu: "https://<keycloak-host>/realms/<realm>/protocol/openid-connect/token"`, and `iat`.
   - Signature: Signed with the client's private key.
3. **Client HTTP Request:**
   - Header added: `DPoP: <DPoP-Proof-JWT>`
   - Body: `grant_type=client_credentials&client_id=<id>&client_secret=<secret>`
4. **Server Validation:**
   - Keycloak validates the signature using the embedded `jwk`.
   - Validates `htm` matches `"POST"` and `htu` matches the token endpoint URI.
   - Validates `typ` is exactly `"dpop+jwt"`.
   - Ensures `jti` is unique (uniqueness check/cache) and `iat` is within a narrow window.
5. **Server Token Emission:**
   - Keycloak generates the access token.
   - Keycloak computes the JWK thumbprint (`jkt`) of the client's public key (per RFC 7638).
   - Keycloak embeds the thumbprint into the access token payload as:
     `"cnf": { "jkt": "<base64url-thumbprint>" }`
   - Keycloak responds with a JSON body:
     ```json
     {
       "access_token": "eyJhbGciOi...",
       "token_type": "DPoP",
       "expires_in": 300,
       "refresh_token": "..."
     }
     ```
     *Notice that `token_type` is `"DPoP"`, indicating that resource servers must require DPoP proofs for this token.*

---

### 2.2 Flow B: Requesting a Protected Resource (e.g., KAS Endpoint)
1. **Compute Access Token Hash (`ath`):**
   - The client takes the raw access token string (e.g., `"eyJhbGciOi..."`).
   - Computes the SHA-256 hash of its ASCII bytes.
   - Encodes the hash using Base64url (no padding). This string is the `ath` claim.
2. **Client DPoP Proof Generation:**
   - Header: Contains `typ: "dpop+jwt"`, signature `alg`, and public key `jwk`.
   - Payload: Contains `jti`, `htm` (e.g., `"POST"`), `htu` (e.g., `"https://kas.example.com/api/kas/v2/rewrap"`), `iat`, and `ath` (computed in Step 1).
   - Signature: Signed with the client's private key.
3. **Client HTTP Request:**
   - Header added: `Authorization: DPoP <access_token>`
   - Header added: `DPoP: <DPoP-Proof-JWT>`
4. **Resource Server (RS) Validation:**
   - The RS extracts the Access Token from `Authorization` and the proof from `DPoP`.
   - RS validates the DPoP proof JWT:
     - Header `typ` is `"dpop+jwt"`.
     - Signature is valid using the embedded `jwk` in the header.
     - `htm` matches the incoming request method and `htu` matches the request URI (excluding query/fragment).
     - `ath` claim in the payload matches the Base64url SHA-256 hash of the incoming access token.
     - `iat` is within range; `jti` is unique/cached.
   - RS validates the Access Token:
     - Token signature, expiration, and active status.
     - Extracts the public key thumbprint from `"cnf": { "jkt": "..." }`.
     - Computes the thumbprint of the embedded `jwk` in the DPoP proof header.
     - **Crucial Match Check:** Asserts that the computed thumbprint of the DPoP proof's public key matches the `jkt` claim inside the access token. If they do not match, the request is rejected with `401 Unauthorized` (sender constraint failed).

---

## 3. Server Nonce Support (DPoP-Nonce)

To defend against clocks that are out-of-sync or replay attacks across long windows, servers can issue a custom "nonce" that the client must echo in its next DPoP proof.

1. **Server Challenge:**
   - If the client sends a DPoP proof without a `nonce` or with an expired `nonce`, the server responds with a `401 Unauthorized` or standard error response, and includes a `DPoP-Nonce` header:
     `DPoP-Nonce: eyJhbGciOi... (opaque string)`
2. **Client Retry:**
   - The client extracts the value of the `DPoP-Nonce` header.
   - It constructs a **new** DPoP proof JWT, adding the `nonce` claim set to that exact value.
   - It signs and retries the HTTP request with the new proof.
3. **Server Verification:**
   - The server verifies that the `nonce` claim matches its current issued/expected nonce.

---

## 4. Client Implementation Requirements (Java & Web SDKs)

### 4.1 Cryptographic Operations
- **Key Pair Management:** SDKs must manage an asymmetric key pair. For maximum compatibility and performance, **EC P-256 (ES256)** is the recommended default. RSA is acceptable but produces larger signatures.
- **JWK Serialisation:** The client must serialize the public key into standard JWK format to place in the `jwk` header parameter.
- **JWK Thumbprint (RFC 7638):** To support caching or internal state matching, the client can compute the SHA-256 JWK thumbprint. Keycloak will also do this to populate the `cnf.jkt` claim.
- **JWT Signing:** The client signs the DPoP proof JWT using the private key.

### 4.2 HTTP Interceptors
- SDKs typically use HTTP clients (e.g., `HttpClient` or `OkHttp` in Java; `fetch` or `axios` in Web SDKs).
- Creating a generic **interceptor** is highly recommended. The interceptor should:
  1. Dynamically read the request HTTP method and target URI.
  2. Retrieve the access token and compute its SHA-256 hash (`ath`) if the token is present (for resource requests).
  3. Create, sign, and inject the `DPoP` header.
  4. Swap the `Authorization: Bearer <token>` header to `Authorization: DPoP <token>`.
  5. Intercept `401` errors containing `DPoP-Nonce` headers, save the nonce, regenerate the proof, and retry the request automatically.
