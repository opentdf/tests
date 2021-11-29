# Protected Data Format Reference Services · [![CI](https://github.com/opentdf/backend/actions/workflows/build.yml/badge.svg)](https://github.com/opentdf/backend/actions?query=event%3Apush+branch%3Amain)


This repository is for a reference implementation of the [openTDF REST Services](https://github.com/opentdf/spec), and sufficient tooling and testing to support the development of it.

## Monorepo

We store several services combined in a single git repository for ease of development. Thse include:

- [Key Access Service](containers/kas/kas_core/)
- Authorization Services
  - [Attributes](containers/service_attribute_authority/)
  - [Entitlements](containers/service_entitlement)
  - [Keycloak Claims Mapper](containers/keycloak-protocol-mapper)
- Tools and shared libraries
- Helm charts for deploying to kubernetes
- Integration tests

### Monorepo structure

1. The `containers` folder contains individual containerized services in folders, each of which should have a `Dockerfile`
1. The build context for each individual containerized service _should be restricted to the folder of that service_ - shared dependencies should either live in a shared base image, or be installable via package management.

## Quick Start and Development

This quick start guide is primarily for development and testing the EAS and KAS infrastructure. See [Production](#production) for details on running in production.

### Tilt

https://tilt.dev

#### Install

https://docs.tilt.dev/install.html

`brew install tilt-dev/tap/tilt`

#### Usage

##### Local Quickstart

```shell
# Install pre-requisites (drop what you've already got)
./tools/pre-reqs docker helm tilt kind octant

# Generate local certs in certs/ directory
./tools/genkeys-if-needed

# Create a local cluster, using e.g. kind
kind create cluster --name opentdf

# start
tilt up --context kind-opentdf

# Hit spacebar to open web UI

# stop and cleanup
tilt down
```

> (Optional) Run `octant` -> This will open a browser window giving you an overview of your local cluster.

### PR builds

When you open a Github PR, an Argo job will run which will publish all Etheria images and Helm charts to Virtru's image/chart
repos under the git shortSha of your PR branch.

To add the Virtru Helm chart repo (one time step)

``` sh
helm repo add virtru https://charts.production.virtru.com
helm repo update
```

> NOTE: Docker images are tagged with longSha, Helm charts are tagged with shortSha
> NOTE: You can check the Argo build output to make sure you're using the same SHAs that Argo published.

This means you can fetch any resource built from your PR branch by appending your SHA.

For instance, if Argo generated a shortSha of `b616e2f`, to fetch the KAS chart for that branch, you would run

`helm pull virtru/kas --version 0.4.4-rc-$(git rev-parse --short HEAD) --devel`

Or, if you wanted to install all of Etheria, you could fetch the top-level chart (which will have all subcharts and images updated to the current PR branch's SHA)

`helm pull virtru/etheria --version 0.1.1-rc-b616e2f --devel`

### (Deprecated) Local `docker-compose`

If you don't want to fool with `minikube`, you can still stand everything up using `docker-compose` - this is not recommended
going forward, but it's an option if you want it.

For this mode, we use docker-compose to compose the EAS and KAS services. Part of this process is putting them behind a reverse proxy.
During this process you will be generating keys for EAS, KAS, the reverse proxy, Certificate Authority (CA), and optionally client certificate.

_Note: This quick start guide is not intended to guide you on using pre-generated keys. Please see [Production]

```sh
./tools/genkeys-if-needed
. certs/.env
export {EAS,KAS{,_EC_SECP256R1}}_{CERTIFICATE,PRIVATE_KEY}
docker compose up -e EAS_CERTIFICATE,EAS_PRIVATE_KEY,KAS_CERTIFICATE,KAS_PRIVATE_KEY,KAS_EC_SECP256R1_CERTIFICATE,KAS_EC_SECP256R1_PRIVATE_KEY --build
```

> Note: OIDC-enabled deployments do not use the flows described below, or docker-compose - they're purely Helm/Minikube based and exclude deprecated services like EAS.
> Refer to the [OIDC Readme](README-keycloak-idp.md) for instructions on how to deploy Eternia with Keycloak and OIDC.

## Installation in Isolated Kubernetes Clusters

If you are working on a kubernetes cluster that does not have access to the Internet,
the `tools/build-offline-bundle` script can generate an archive of all backend services.

### Building the offline bundle

To build the bundle, on a connected server that has recent (2021+) versions of the following tools
(some of which may be installed with `tools/pre-reqs` on linux and macos):

- The bash shell
- git
- docker
- helm
- python
- curl
- npm (for abacus)

Running the `tools/build-offline-bundle` script will create a zip file in the `build/` folder named `offline-bundle-[date]-[short digest].zip.

Another script, `tools/test-offline-bundle`, can be used to validate that a build was created and can start, using a local k8s cluster created with kind.

#### NB: Including Third Party Libraries

The current third party bundles, kind and postgresql, may require manual editing of the `build-offline-bundle` script to get the appripriate tag and SHA hash. See within the script for notes.

### Using the offline bundle

The offline bundle includes:

- Images
- Charts

### Install images locally

The images are installed in separate files.
opentdf-service-images-[tag].tar includes all the opentdf custom backend microservices.
third-party-image-service-[tag].tar includes individual images of various required and optional third party services. For the configuration we describe here, we require only the postgresql image.

These images must be made available to your cluster's registry. One way to do this is to first install them to a local docker registry, and then push them to a remote registry, using `docker load` and `docker push`.


```sh
docker load export/*.tar
docker images --format="{{json .Repository }}"  | sort | uniq | tr -d '"'| grep ^virtru/tdf | while read name; do docker push $name; done
```

### Configuring the backend

To install the app, we need to configure the helm values to match the configuration of your system, and to include secrets that are unique to your installation.

#### Secrets

For this example, we will use self signed certificates and secrets:

```sh
export/tools/genkeys-if-needed
kubectl create secret generic etheria-secrets \
    "--from-file=EAS_PRIVATE_KEY=export/certs/eas-private.pem" \
    "--from-file=EAS_CERTIFICATE=export/certs/eas-public.pem" \
    "--from-file=KAS_EC_SECP256R1_CERTIFICATE=export/certs/kas-ec-secp256r1-public.pem" \
    "--from-file=KAS_CERTIFICATE=export/certs/kas-public.pem" \
    "--from-file=KAS_EC_SECP256R1_PRIVATE_KEY=export/certs/kas-ec-secp256r1-private.pem" \
    "--from-file=KAS_PRIVATE_KEY=export/certs/kas-private.pem" \
    "--from-file=ca-cert.pem=export/certs/ca.crt" || e "create etheria-secrets failed"
```

We will also need to generate and use a custom postgres password.

```sh
POSTGRES_PW=$(openssl rand -base64 40)
sed -i '' "s/myPostgresPassword/${POSTGRES_PW}/" export/deployment/values-postgresql-tdf.yaml
kubectl create secret generic attribute-authority-secrets --from-literal=POSTGRES_PASSWORD="${POSTGRES_PW}"
kubectl create secret generic entitlement-secrets --from-literal=POSTGRES_PASSWORD="${POSTGRES_PW}"
```

> TODO: Move keycloak creds into secrets.

#### Names and Values

##### `values-all-in-one`: Primary backend configuration

Replace the values for `host` and `kasDefaultUrl` with your public domain name.

> TODO: Migrate into a true umbrella charts, to include the ability to set a single host

##### `values-postgresql-tdf`: Advanced Postgres Configuration

This should be left alone, but may be edited as needed for insight into postres, or schema upgrades.

### Helm Installation

From the export folder, run:

```sh
TAG=$(<BUNDLE_TAG)
helm upgrade --install keycloak charts/keycloak-15.0.1.tgz -f deployment/values-virtru-keycloak.yaml --set image.tag=${TAG}
helm upgrade --install etheria charts/etheria -f deployment/values-all-in-one.yaml
```



## Swagger-UI

KAS and EAS servers support Swagger UI to provide documentation and easier interaction for the REST API.  
Add "/ui" to the base URL of the appropriate server. For example, `http://127.0.0.1:4010/ui/`.
KAS and EAS each have separate REST APIs that together with the SDK support the full TDF3 process for encryption,
authorization, and decryption.

Swagger-UI can be disabled through the SWAGGER_UI environment variable. See the configuration sections of the
README documentation for [KAS](kas_app/README.md) and [EAS](eas/README.md) in this repository.

## Committing Code

Please use the autoformatters included in the tools directory. To get them
running in git as a pre-commit, use the following:

```sh
tools/black --install
tools/shfmt --install
```

These commands will autoformat python and bash scripts after you run 'git commit' but before
the commit is written to the tree. Then mail a PR and follow the advice on the PR template.

## Testing

### Unit Tests

Our unit tests use pytest, and should integrate with your favorite environment.
For continuous integration, we use `monotest`, which runs
all the unit tests in a python virtual environment.

To run all the unit tests in the repo:

``` shell
tools/monotest all
```

To run a subset of unit tests (e.g. just the `kas_core` tests from the [kas_core](kas_core) subfolder):

``` shell
tools/monotest kas_core
```

### Cluster tests

Our E2E cluster tests use [kuttl](https://kuttl.dev/docs/cli.html#setup-the-kuttl-kubectl-plugin), and you can run them
against an instance of Etheria deployed to a cluster (local minikube, or remote)

1. Install Etheria to a Kubernetes cluster (using the quickstart method above, for example)
1. Install [kuttl](https://kuttl.dev/docs/cli.html#setup-the-kuttl-kubectl-plugin)
1. From the repo root, run `kubectl kuttl test tests/cluster`
1. For advanced usage and more details, refer to [tests/cluster/README.md](tests/cluster/README.md)

> Etheria's CI is not currently cluster based, and so the kuttl tests are not being run via CI - this should be corrected when the CI is moved to K8S/Argo.


#### Security test

Once a cluster is running, run `security-test/helm-test.sh`
### Integration Tests

You can run a complete integration test locally using docker compose with the `docker-compose.ci.yml`, or with the `docker-compose.pki-ci.yml` to use the PKI keys you generated earlier. A helper script is available to run both sets of integration tests, `xtest/scripts/test-in-containers`.

To run a local integration test with the test harness running in
in the host machine, and not in a container, you may do the following:

```sh
docker-compose -f docker-compose.yml up --build
cd xtest
python3 test/runner.py -o Alice_1234 -s local --sdk sdk/py/oss/cli.sh
```

To test docker-compose using SDK and Python versions, create a .env

```dotenv
PY_OSS_VERSION===1.1.1
PY_SDK_VERSION=3.9
NODE_VERSION=14
```

### Performance, and End-to-end Tests

```shell script
docker-compose --env-file certs/.env --file performance-test/docker-compose.yml up --build --exit-code-from performance-test performance-test

docker-compose --env-file certs/.env --file e2e-test/docker-compose.yml up --build --exit-code-from e2e-test e2e-test
```

## Logs

In development Docker Compose runs in a attached state so logs can be seen from the terminal.

In a detached state logs can be accessed via [docker-compose logs](https://docs.docker.com/compose/reference/logs/)

Example:

```
> docker-compose logs kas
Attaching to kas
kas        | Some log here
```

## Deployment

TBD - Etheria deployment will be done to Kubernetes clusters via Helm chart.
TBD - for an idea of what's involved in this, including what Helm charts are required, [check the local install script](~/Source/etheria/deployments/local/start.sh)

### (Deprecated) Docker Compose Deployment

With Docker Compose deployment is [made easy with Docker Swarm](https://docs.docker.com/engine/swarm/stack-deploy/).

### (Deprecated) Configuration

Deployment configuration can be done through `docker-compose.yml` via the environment property.

#### Workers

The number of worker processes for handling requests.

A positive integer generally in the 2-4 x \$(NUM_CORES) range. You'll want to vary this a bit to find the best for your particular application's work load.

By default, the value of the WEB_CONCURRENCY environment variable. If it is not defined, the default is 1.

#### Threads

The number of worker threads for handling requests.

Run each worker with the specified number of threads.

A positive integer generally in the 2-4 x \$(NUM_CORES) range. You'll want to vary this a bit to find the best for your particular application's work load.

If it is not defined, the default is 1.

This setting only affects the Gthread worker type.

#### Profiling

https://gist.github.com/michaeltcoelho/c8bc65e5c3dce0f85312349353bf155a

https://docs.python.org/3/using/cmdline.html#environment-variables

### Advanced Manual setup

It's better to use one of the [above methods](#local-quickstart) for setup, but this explains the step by step details of how
the above methods work, and is included here for completeness.

#### Generate Keys

**WARNING: By generating new certs you will invalidate existing entity objects.**

##### Quick Start

To assist in quickly starting use the `./tools/genkeys-if-needed` to build all the keys. The hostname will be assigned `etheria.local`.
Make sure to add `127.0.0.1           etheria.local` to your `/etc/hosts` or `c:\windows\system32\drivers\etc\hosts`.

Additionally you can set a custom hostname `ETHERIA_HOSTNAME=myhost.com ./tools/genkeys-if-needed`, but you might have to update the docker-compose files.

_If you need to customization please see the Advanced Usage guide alongside the Genkey Tools._

1. Decide what your host name will be for the reverse proxy will be (e.g. example.com)
2. Generate reverse proxy certs `./tools/genkey-reverse-proxy $HOSTNAME_OF_REVERSE_PROXY`
3. Generate EAS & KAS certs `./tools/genkey-apps`
4. (Optional) Generate client certificates `./tools/genkey-client` for PKI support

##### Genkey Tools

Each genkey tools each have a brief help which you can access like

- `./tools/genkey-apps --help`
- `./tools/genkey-client --help`
- `./tools/genkey-reverse-proxy --help`

#### Start Services (non-PKI)

1. Update `docker-compose.yml` to use the reverse-proxy CN you defined above rather than `localhost`
1. Run:

```sh
. certs/.env
export {EAS,KAS{,_EC_SECP256R1}}_{CERTIFICATE,PRIVATE_KEY}
docker compose up -e EAS_CERTIFICATE,EAS_PRIVATE_KEY,KAS_CERTIFICATE,KAS_PRIVATE_KEY,KAS_EC_SECP256R1_CERTIFICATE,KAS_EC_SECP256R1_PRIVATE_KEY --build
```

_To learn more about [docker-compose see the manual](https://docs.docker.com/compose/reference/up/)._

#### Start Services in PKI mode

If you need support for PKI you can follow these steps.
There are a few requirements for starting in PKI mode:

1. Must create reverse proxy certificates with a CA
2. Must create a client certificate signed with CA
3. (Optional) Install CA and client certificate to OS keychain (_Please search the internet for instructions_)

Requirements (1) and (2) are described in [generate keys](#generate-keys) above.

`docker-compose -f docker-compose.pki.yml up --build`

## Production

_TBD_

[^1]: https://docs.docker.com/compose/reference/logs/
