# Entitlements

## Development

### Start database

see [migration](../migration/README.md)

### Configure server
```shell
export POSTGRES_HOST=localhost
export POSTGRES_USER=tdf_entitlement_manager
export POSTGRES_PASSWORD=myPostgresPassword
export POSTGRES_DATABASE=tdf_database
export POSTGRES_SCHEMA=tdf_entitlement
export SERVER_LOG_LEVEL=DEBUG
```

### Start Server
```shell
cd containers
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install --requirement entitlements/requirements.txt
python3 -m uvicorn containers.entitlements.main:app --reload --port 4030
```

### Extract OpenAPI
```shell
./scripts/openapi-generator
```

### View API

#### Swagger UI
http://localhost:4030/docs

#### ReDoc
http://localhost:4030/redoc

## Kubernetes

### build image
```shell
# from project root
docker build --no-cache --tag opentdf/entitlements:0.2.0 entitlements
```

### secrets
```shell
kubectl create secret generic entitlements-secrets --from-literal=POSTGRES_PASSWORD=myPostgresPassword
```

### helm
```shell
# from project root
helm upgrade --install entitlements ./charts/entitlements --debug
```
