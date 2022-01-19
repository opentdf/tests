# Abacus

ENV VARIABLES to use:

* REACT_APP_SERVER_DATA={'clientId':'','realm':''}
* REACT_APP_BASE_URL =
* REACT_APP_KEYCLOAK_HOST =
* REACT_APP_ENTITLEMENTS_HOST =
* REACT_APP_ATTRIBUTES_HOST =

## Development

### OpenAPI

Generate TypeScript types from OpenAPI specifications
reference https://github.com/drwpow/openapi-typescript

```shell
npx openapi-typescript ../../service_attribute_authority/openapi.json --output src/attributes.ts
npx openapi-typescript ../../service_entitlement/openapi.json --output src/entitlement.ts
```

Keycloak
reference https://github.com/ccouzens/keycloak-openapi

```shell
npx openapi-typescript https://raw.githubusercontent.com/ccouzens/keycloak-openapi/main/keycloak/15.0.json --output src/service/keycloak.ts
```
