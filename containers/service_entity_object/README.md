
## development

### environment variables
```shell
export POSTGRES_HOST=localhost
export POSTGRES_USER=tdf_entitlement_reader
export POSTGRES_PASSWORD=myPostgresPassword
export POSTGRES_DATABASE=tdf_database
export POSTGRES_SCHEMA=tdf_entitlement
# app
export EAS_ENTITY_EXPIRATION=120
export KAS_DEFAULT_URL="http://localhost:8000"
# secrets
# Get secrets from certs/.env created from `scripts/genkeys-if-needed`
export EAS_PRIVATE_KEY=""
export KAS_CERTIFICATE=""
export KAS_EC_SECP256R1_CERTIFICATE=""
```

### server
```shell
pipenv install
pipenv run uvicorn main:app --reload --port 4010
```

### OpenAPI
```shell
pipenv run python3 main.py > openapi.json
```


### postgres using Docker
```shell
docker run --rm -p 5432:5432 -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=myPostgresPassword -e POSTGRES_DB=tdf_database postgres:12
```

## kubernetes

### build image
```shell
# from project root
docker build --no-cache --tag virtru/tdf-entity-object-service:0.2.0 service_entity_object
```

### secrets
```shell
kubectl create secret generic entity-object-secrets \
  --from-literal=POSTGRES_PASSWORD=myPostgresPassword \
  --from-file=EAS_PRIVATE_KEY=certs/eas-private.pem \
  --from-file=KAS_CERTIFICATE=certs/kas-public.pem \
  --from-file=KAS_EC_SECP256R1_CERTIFICATE=certs/kas-ec-secp256r1-public.pem
```

### helm
```shell
# from project root
helm upgrade --install entity-object ./charts/service_entity_object --debug
```
