# Attributes

## Development

### Start database

see [migration](../migration/README.md)

### Configure server
```shell
export POSTGRES_HOST=localhost
export POSTGRES_USER=tdf_attribute_manager
export POSTGRES_PASSWORD=myPostgresPassword
export POSTGRES_DATABASE=postgres
export POSTGRES_SCHEMA=tdf_attribute
export SERVER_LOG_LEVEL=DEBUG
```

### Start Server
```shell
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install --requirement requirements.txt
python3 -m uvicorn main:app --reload --port 4020
```

### Extract OpenAPI
```shell
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install --requirement requirements.txt
python3 main.py > openapi.json
```

### View API

#### Swagger UI
http://localhost:4020/docs

#### ReDoc
http://localhost:4020/redoc


## Kubernetes

### build image
```shell
# from project root
docker build --no-cache --tag opentdf/attributes:0.2.0 attributes
```

### secrets
```shell
kubectl create secret generic attributes-secrets --from-literal=POSTGRES_PASSWORD=myPostgresPassword
```

### helm
```shell
# from project root
helm upgrade --install attributes ./charts/attributes --debug
```

### ingress
```shell
kubectl --filename=deployments/pki_local/nginx.ingress.yaml
```
