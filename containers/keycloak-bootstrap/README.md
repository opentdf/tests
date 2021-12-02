# Keycloak Bootstrap Configuration

We use a Python wrapper around Keycloak's REST API
to automatically configure Keycloak for Virtru's needs.

## Build and Setup

Docker image names and version tags are set in `Makefile`.

### Build An Attribute Provider Docker Container

```
$ make
```

### Build A Docker Container, Push To Container Repo

```
$ make dockerbuildpush
```

### Build, Test, And Run A Local Attribute Provider Virtualenv

```
$ make localbuild
$ make test
$ export keycloak_hostname=http://localhost:8080
$ export keycloak_admin_username=admin
$ export keycloak_admin_password=admin
$ make run
pipenv run ./bootstrap.py
...
DEBUG:keycloak_bootstrap:Login admin http://localhost:8080/auth/ admin
INFO:keycloak_bootstrap:Create realm tdf
DEBUG:keycloak_bootstrap:Create client tdf-client
INFO:keycloak_bootstrap:Created client 7d157a38-faa0-443d-91fa-130abbf5043a
```
