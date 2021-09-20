## Base

### Base build image

#### Docker Hub
https://hub.docker.com/repository/docker/virtru/etheria-base-build

#### Buildkite
https://buildkite.com/virtru/etheria-base

#### Local build
```shell
cd service_base
docker build --tag virtru/etheria-base-build .
```

#### Update requirements.txt
```shell
cd service_entity_object
pipenv lock --keep-outdated --requirements > ../service_base/requirements.txt
```