# Abacus

## Development

### OpenAPI

Generate TypeScript types from OpenAPI specifications
reference https://github.com/drwpow/openapi-typescript

```shell
npx openapi-typescript https://raw.githubusercontent.com/opentdf/backend/main/containers/service_attribute_authority/openapi.json --output src/attributes.ts

npx openapi-typescript https://raw.githubusercontent.com/opentdf/backend/main/containers/service_entitlement/openapi.json --output src/entitlement.ts

npx openapi-typescript /Users/paulflynn/Projects/opentdf/backend/containers/attributes/openapi.json --output src/attributes.ts

npx openapi-typescript /Users/paulflynn/Projects/opentdf/backend/containers/entitlements/openapi.json --output src/entitlement.ts

# typescript-fetch config options
#https://openapi-generator.tech/docs/generators/typescript-fetch

# entitlements
mkdir -p build/entitlements
cp /Users/paulflynn/Projects/opentdf/backend/containers/entitlements/openapi.json build/entitlements/openapi.json
docker run --rm -v "${PWD}/build:/build" openapitools/openapi-generator-cli generate \
    --generate-alias-as-model \
    --remove-operation-id-prefix \
    --additional-properties withInterfaces=true \
    -i build/entitlements/openapi.json \
    -g typescript-fetch \
    -o /build/entitlements
    
# attributes
mkdir -p build/attributes
cp /Users/paulflynn/Projects/opentdf/backend/containers/attributes/openapi.json build/attributes/openapi.json
docker run --rm -v "${PWD}/build:/build" openapitools/openapi-generator-cli generate \
    --additional-properties withInterfaces=true \
    -i build/attributes/openapi.json \
    -g typescript-fetch \
    -o /build/attributes
```

Keycloak  
reference https://github.com/ccouzens/keycloak-openapi

```shell
npx openapi-typescript https://raw.githubusercontent.com/ccouzens/keycloak-openapi/main/keycloak/15.0.json --output src/service/keycloak.ts
```

### Docker

#### Build
```shell
docker build --tag opentdf/abacus .
docker tag opentdf/abacus opentdf/abacus:0.2.0
docker push opentdf/abacus:0.2.0 
```
