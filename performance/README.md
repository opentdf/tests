# PPerformance

## Prerequisites

```shell
brew install k6
```

## Execute

```shell
# Basic run with default endpoints
k6 run authorization-client.js

k6 run authorization-client.js --vus 100 --duration 1m

# Run with custom endpoints
k6 run authorization-client.js --vus 100 --duration 1m \
  --env AUTH_URL=http://keycloak.example.com/auth/realms/myrealm/protocol/openid-connect/token \
  --env API_URL=https://api.example.com

# Complete configuration with all parameters
k6 run authorization-client.js --vus 100 --duration 2m \
  --env TOTAL_VUS=100 \
  --env AUTH_URL=https://keycloak.dsp-stg-green.virtru.com/realms/opentdf-stg/protocol/openid-connect/token \
  --env API_URL=https://platform.dsp-stg-green.virtru.com/ \
  --env KEYCLOAK_URL=https://keycloak.dsp-stg-green.virtru.com \
  --env REALM=opentdf-stg
  
  # Complete configuration with all parameters
k6 run authorization-client.js \
  --env AUTH_URL=https://keycloak.dsp-stg-green.virtru.com/realms/opentdf-stg/protocol/openid-connect/token \
  --env API_URL=https://platform.dsp-stg-green.virtru.com/ \
  --env KEYCLOAK_URL=https://keycloak.dsp-stg-green.virtru.com \
  --env REALM=opentdf-stg
```
