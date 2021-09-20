
## development

### environment variables
```shell
export POSTGRES_HOST=localhost
export POSTGRES_USER=tdf_entity_manager
export POSTGRES_PASSWORD=myPostgresPassword
export POSTGRES_DATABASE=tdf_database
export POSTGRES_SCHEMA=tdf_entity
```

### server
```shell
pipenv install
pipenv run uvicorn main:app --reload --port 4040
```

## kubernetes

### build image
```shell
# from project root
docker build --no-cache --tag virtru/tdf-entity-service:0.2.0 service_entity
```

### secrets
```shell
kubectl create secret generic entity-secrets --from-literal=POSTGRES_PASSWORD=myPostgresPassword
```

### helm
```shell
# from project root
helm upgrade --install entity ./charts/service_entity --debug
```
