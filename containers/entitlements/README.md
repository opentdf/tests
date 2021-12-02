
## development

### environment variables
```shell
export POSTGRES_HOST=localhost
export POSTGRES_USER=tdf_entitlement_manager
export POSTGRES_PASSWORD=myPostgresPassword
export POSTGRES_DATABASE=tdf_database
export POSTGRES_SCHEMA=tdf_entitlement
```

### server
```shell
pipenv install
pipenv run uvicorn main:app --reload --port 4030
```

### OpenAPI
```shell
pipenv run python3 main.py > openapi.json
```

## kubernetes

### build image
```shell
# from project root
docker build --no-cache --tag virtru/tdf-entitlements-service:0.2.0 entitlements
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

## design
TODO add assumptions of how it is used

TODO link to sqlalchemy for horizontal sharding
https://arxiv.org/pdf/1406.2294.pdf
