
## development

### environment variables
```shell
export POSTGRES_HOST=localhost
export POSTGRES_USER=tdf_attribute_manager
export POSTGRES_PASSWORD=myPostgresPassword
export POSTGRES_DATABASE=tdf_database
export POSTGRES_SCHEMA=tdf_attribute
```

### server
```shell
pipenv install
pipenv run uvicorn main:app --reload --port 4020
```

### OpenAPI
```shell
pipenv run python3 main.py > openapi.json
```

## kubernetes

### build image
```shell
# from project root
docker build --no-cache --tag virtru/tdf-attribute-authority-service:0.2.0 service_attribute_authority
```

### secrets
```shell
kubectl create secret generic attribute-authority-secrets --from-literal=POSTGRES_PASSWORD=myPostgresPassword
```

### helm
```shell
# from project root
helm upgrade --install attribute-authority ./charts/service_attribute_authority --debug
```

### ingress
```shell
kubectl --filename=deployments/pki_local/nginx.ingress.yaml
```
