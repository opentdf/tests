# Claims

The claims service provides `claims` JSON blobs to an identity provider. We
currently are using Keycloak as the IdP.

1. Upon successful client authentication via tge IdP, Keycloak, that service
   runs a plugin to invoke this service.
2. An instance of the Claims service processes the request. It creates a
   Claims Object appropriate for that client in the current context,
   and returns it to the IdP/Keycloak.
3. Our IdP then returns a signed JWT with the Claims Object
   inside.

## Development

### Start database

see [migration](../migration/README.md)

### Configure server
```shell
export POSTGRES_HOST=localhost
export POSTGRES_USER=tdf_entitlement_reader
export POSTGRES_PASSWORD=myPostgresPassword
export POSTGRES_DATABASE=tdf_database
export POSTGRES_SCHEMA=tdf_entitlement
```

### server
```shell
cd containers
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install --requirement attributes/requirements.txt
python3 -m uvicorn attributes.main:app --reload --port 5000
```

### OpenAPI
```shell
./scripts/openapi-generator
```


### postgres using Docker
```shell
docker run --rm -p 5432:5432 -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=myPostgresPassword -e POSTGRES_DB=tdf_database postgres:12
```

## kubernetes

### build image
```shell
# from project root
docker build --no-cache --tag opentdf/claims:0.2.0 claims
```

### secrets
```shell
kubectl create secret generic claims-secrets \
  --from-literal=POSTGRES_PASSWORD=myPostgresPassword \
  --from-file=KAS_CERTIFICATE=certs/kas-public.pem \
  --from-file=KAS_EC_SECP256R1_CERTIFICATE=certs/kas-ec-secp256r1-public.pem
```

### helm
```shell
# from project root
helm upgrade --install claims ./charts/claims --debug
```
