#!/usr/bin/env bash
set -euo pipefail

# Since token exchange only is used for public (read: browser) clients, we can't use `sdk-cli` or node flows to test
# This contrived example is better than nothing:

# Get the first token
printf "\nKUTTL: Request token:\n'"
ACCESS_TOKEN=$(curl --location --request POST "$VIRTRU_OIDC_ENDPOINT/auth/realms/tdf/protocol/openid-connect/token" \
  --header 'Authorization: AWS4-HMAC-SHA256 Credential=AKIAWM2OYTV3QKEQ455I/20210105/us-east-1/s3/aws4_request, SignedHeaders=amz-sdk-invocation-id;amz-sdk-retry;content-type;host;user-agent;x-amz-content-sha256;x-amz-date, Signature=87bade2cc60837859a7cc61ffd678401ed477630ac9e075c67b4ee66b7fc8aa7' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=password' \
  --data-urlencode 'client_id=tdf-client' \
  --data-urlencode 'client_secret=123-456' \
  --data-urlencode 'username=user1' \
  --data-urlencode 'password=password' | jq -r '.access_token')

# Exchange it
printf "\nKUTTL: Exchange token with Keycloak:\n'"
EXCHANGE_TOKEN=$(curl --location --request POST "$VIRTRU_OIDC_ENDPOINT/auth/realms/tdf/protocol/openid-connect/token" \
  --header 'Authorization: AWS4-HMAC-SHA256 Credential=AKIAWM2OYTV3QKEQ455I/20210105/us-east-1/s3/aws4_request, SignedHeaders=amz-sdk-invocation-id;amz-sdk-retry;content-type;host;user-agent;x-amz-content-sha256;x-amz-date, Signature=87bade2cc60837859a7cc61ffd678401ed477630ac9e075c67b4ee66b7fc8aa7' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --header 'X-VirtruPubkey: REALCERT' \
  --data-urlencode 'grant_type=urn:ietf:params:oauth:grant-type:token-exchange' \
  --data-urlencode 'client_id=tdf-client' \
  --data-urlencode 'client_secret=123-456' \
  --data-urlencode "subject_token=$ACCESS_TOKEN" \
  --data-urlencode 'audience=tdf-client' | jq -r '.access_token')

# This should succeed
printf "\nKUTTL: Validate exchanged token with Keycloak:\n'"
curl --location --request POST "$VIRTRU_OIDC_ENDPOINT/auth/realms/tdf/protocol/openid-connect/userinfo" \
  --header "Authorization: Bearer $EXCHANGE_TOKEN" \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=client_credentials' \
  --data-urlencode 'client_id=tdf-client' \
  --data-urlencode 'client_secret=123-456'
