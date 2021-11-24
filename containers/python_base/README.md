## Base

### Base build image

#### Docker Hub
https://hub.docker.com/repository/docker/virtru/tdf-python-base

#### Buildkite
https://buildkite.com/virtru/etheria-base

#### Local build
```shell
cd service_base
docker build --tag virtru/tdf-python-base .
```

#### Update requirements.txt
```shell
cd service_entity_object
pipenv lock --keep-outdated --requirements > ../service_base/requirements.txt
```