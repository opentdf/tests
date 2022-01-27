# Abacus

## Development

### Setup

Create a `.env` with your values
```dotenv
REACT_APP_SERVER_DATA={'attributes':'','entitlements':'','access':'','authority':'','clientId':'','realm':''}
```

### Server (development)

Starts server on http://localhost:3000  
`npm run start`

### Server (production)

```shell
docker run -p 3000:80 \
  -e KEYCLOAK_HOST="http://localhost/auth/" \
  -e KEYCLOAK_CLIENT_ID="localhost-abacus" \
  -e KEYCLOAK_REALM="opentdf-realm" \
  -e ATTRIBUTES_HOST="http://localhost/v2/attributes" \
  -e ENTITLEMENTS_HOST="http://localhost/v2/entitlements" \
  $(docker build -q .)
```

### OpenAPI

Generate TypeScript types from OpenAPI specifications  
reference https://github.com/drwpow/openapi-typescript

```shell
npx openapi-typescript https://raw.githubusercontent.com/opentdf/backend/main/containers/service_attribute_authority/openapi.json --output src/attributes.ts
npx openapi-typescript https://raw.githubusercontent.com/opentdf/backend/main/containers/service_entitlement/openapi.json --output src/entitlement.ts
```

Keycloak  
reference https://github.com/ccouzens/keycloak-openapi

```shell
npx openapi-typescript https://raw.githubusercontent.com/ccouzens/keycloak-openapi/main/keycloak/15.0.json --output src/service/keycloak.ts
```

### Build and deploy

```shell
docker build --tag opentdf/abacus .
docker tag opentdf/abacus opentdf/abacus:0.2.0
docker push opentdf/abacus:0.2.0 
```

### Test

#### react-scripts test
`npm run test`

#### Playwright Test

To install  
`npx playwright install` 

To run (while development server above is running)  
`npm run test:playwright`
