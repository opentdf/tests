## Base

### Base build image

#### Docker Hub
https://hub.docker.com/repository/docker/opentdf/python-base

#### Buildkite
https://buildkite.com/virtru/etheria-base

#### Local build
```shell
cd service_base
docker build --tag opentdf/python-base .
```

#### Update requirements.txt
```shell
cd python_base
pipenv lock --keep-outdated --requirements > ../service_base/requirements.txt
```