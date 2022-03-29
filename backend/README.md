# Protected Data Format Reference Services · [![CI](https://github.com/opentdf/backend/actions/workflows/build.yaml/badge.svg)](https://github.com/opentdf/backend/actions/workflows/build.yaml) · [![Code Quality](https://sonarcloud.io/api/project_badges/measure?project=opentdf_backend&metric=alert_status&token=4fff8ae1ff25f2ed30b5705197309bd4affbd9f1)](https://sonarcloud.io/summary/new_code?id=opentdf_backend)


This repository is for a reference implementation of the [openTDF REST Services](https://github.com/opentdf/spec), and sufficient tooling and testing to support the development of it.

## Monorepo

We store several services combined in a single git repository for ease of development. Thse include:

- [Key Access Service](containers/kas/kas_core/)
- Authorization Services
  - [Attributes](containers/attributes/)
  - [Entitlements](containers/entitlements)
  - [Keycloak Claims Mapper](containers/keycloak-protocol-mapper)
- Tools and shared libraries
- Helm charts for deploying to kubernetes
- Integration tests

### Monorepo structure

1. The `containers` folder contains individual containerized services in folders, each of which should have a `Dockerfile`
1. The build context for each individual containerized service _should be restricted to the folder of that service_ - shared dependencies should either live in a shared base image, or be installable via package management.
1. Integration tests are stored in the `tests` folder. Notably, a useful integration test (x86 only) is available by running `cd tests/integration && tilt ci`
1. A simple local stack can be pulled up with the latest releases of the images by running `tilt up` from the root. To use the latest mainline branches, edit the `CONTAINER_REGISTRY` to point to `ghcr.io` and [follow github's instructions to log into that repository](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-to-the-container-registry).

## Quick Start and Development

This quick start guide is primarily for development and testing the ABAC and KAS infrastructure. See [Production](#production) for details on running in production.

### Prerequisites

- Install [Docker](https://www.docker.com/)
    - see https://docs.docker.com/get-docker/

- Install [kubectl](https://kubernetes.io/docs/reference/kubectl/overview/)
    - On macOS via Homebrew: `brew install kubectl`
    - Others see https://kubernetes.io/docs/tasks/tools/

- Install a local Kubernetes manager. Options include minikube and kind. I suggest using `ctlptl` (see below) for managing several local clusters.

  - minikube
    - On macOS via Homebrew: `brew install minikube`
    - Others see https://minikube.sigs.k8s.io/docs/start/

  - Install [kind](https://kind.sigs.k8s.io/)
    - On macOS via Homebrew: `brew install kind`
    - On Linux or WSL2 for Windows: `curl -Lo kind https://kind.sigs.k8s.io/dl/v0.11.1/kind-linux-amd64 && chmod +x kind && sudo mv kind /usr/local/bin/kind`
    - Others see https://kind.sigs.k8s.io/docs/user/quick-start/#installation

- Install [helm](https://helm.sh/)
    - On macOS via Homebrew: `brew install helm`
    - Others see https://helm.sh/docs/intro/install/

- Install [Tilt](https://tilt.dev/)
    - On macOS via Homebrew: `brew install tilt-dev/tap/tilt`
    - Others see https://docs.tilt.dev/install.html

- Install [ctptl](https://github.com/tilt-dev/ctlptl#readme)
  - On macOS via Homebrew: `brew install tilt-dev/tap/ctlptl`
  - Others see https://github.com/tilt-dev/ctlptl#homebrew-maclinux

### Alternative Prerequisites install
```shell
# Install pre-requisites (drop what you've already got)
./scripts/pre-reqs docker helm tilt kind
```

### Generate local certs in certs/ directory

> You may need to manually clean the `certs` folder occasionally

```
./scripts/genkeys-if-needed
```

### Create cluster

```shell
ctlptl create cluster kind --registry=ctlptl-registry --name kind-opentdf
```

### Start cluster

> TODO([PLAT-1599](https://virtru.atlassian.net/browse/PLAT-1599)) Consolidate integration and root tiltfile.

```shell
tilt up # or tilt up -- --to-edit opentdf-abacus if you want to use local frontend
```

# Hit spacebar to open web UI

### Cleanup

```shell
tilt down
ctlptl delete cluster kind-opentdf
helm repo remove keycloak
```

> (Optional) Run `octant` -> This will open a browser window giving you an overview of your local cluster.

## Installation in Isolated Kubernetes Clusters

> TODO([PLAT-1474])(https://virtru.atlassian.net/browse/PLAT-1474)) Update script

If you are working on a kubernetes cluster that does not have access to the Internet,
the `scripts/build-offline-bundle` script can generate an archive of all backend services.

### Building the offline bundle

To build the bundle, on a connected server that has recent (2021+) versions of the following scripts
(some of which may be installed with `scripts/pre-reqs` on linux and macos):

- The bash shell
- git
- docker
- helm
- python
- curl
- npm (for abacus)

Running the `scripts/build-offline-bundle` script will create a zip file in the `build/` folder named `offline-bundle-[date]-[short digest].zip.

Another script, `scripts/test-offline-bundle`, can be used to validate that a build was created and can start, using a local k8s cluster created with kind.

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
export/scripts/genkeys-if-needed
kubectl create secret generic kas-secrets \
    "--from-file=EAS_CERTIFICATE=export/certs/eas-public.pem" \
    "--from-file=KAS_EC_SECP256R1_CERTIFICATE=export/certs/kas-ec-secp256r1-public.pem" \
    "--from-file=KAS_CERTIFICATE=export/certs/kas-public.pem" \
    "--from-file=KAS_EC_SECP256R1_PRIVATE_KEY=export/certs/kas-ec-secp256r1-private.pem" \
    "--from-file=KAS_PRIVATE_KEY=export/certs/kas-private.pem" \
    "--from-file=ca-cert.pem=export/certs/ca.crt" || e "create kas-secrets failed"
```

We will also need to generate and use a custom postgres password.

```sh
POSTGRES_PW=$(openssl rand -base64 40)
sed -i '' "s/myPostgresPassword/${POSTGRES_PW}/" export/deployment/values-postgresql-tdf.yaml
kubectl create secret generic attributes-secrets --from-literal=POSTGRES_PASSWORD="${POSTGRES_PW}"
kubectl create secret generic entitlements-secrets --from-literal=POSTGRES_PASSWORD="${POSTGRES_PW}"
```

> TODO: Move keycloak creds into secrets.

#### Names and Values

##### `values-all-in-one`: Primary backend configuration

Replace the values for `host` and `kasDefaultUrl` with your public domain name.

> TODO: Migrate into a true umbrella charts, to include the ability to set a single host

##### `values-postgresql-tdf`: Advanced Postgres Configuration

This should be left alone, but may be edited as needed for insight into postres, or schema upgrades.

## Swagger-UI

The microservices support OpenAPI, and can provide documentation and easier interaction for the REST API.
Add "/ui" to the base URL of the appropriate server. For example, `http://127.0.0.1:4010/ui/`.
KAS and EAS each have separate REST APIs that together with the SDK support the full TDF3 process for encryption,
authorization, and decryption.

Swagger-UI can be disabled through the SWAGGER_UI environment variable. See the configuration sections of the
README documentation for [KAS](kas/kas_app/README.md) for more detail.

## Committing Code

Please use the autoformatters included in the scripts directory. To get them
running in git as a pre-commit, use the following:

```sh
scripts/black --install
scripts/shfmt --install
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
scripts/monotest
```

To run a subset of unit tests (e.g. just the `kas_core` tests from the [kas_core](kas_core) subfolder):

``` shell
scripts/monotest containers/kas/kas_core
```


### Security test

Once a cluster is running, run `tests/security-test/helm-test.sh`

### Integration Tests

> TODO(PLAT-1619) Add frontend+backend integration test

## Deployment

Any deployments are controlled by downstream repositories, e.g. internal to Virtru or other integrators.

> TODO Reference opentdf.us deployment?

# Customizing your local development experience
#### Quick Start

To assist in quickly starting use the `./scripts/genkeys-if-needed` to build all the keys. The hostname will be assigned `opentdf.local`.
Make sure to add `127.0.0.1           opentdf.local` to your `/etc/hosts` or `c:\windows\system32\drivers\etc\hosts`.

Additionally you can set a custom hostname `BACKEND_SERVICES_HOSTNAME=myhost.com ./scripts/genkeys-if-needed`, but you might have to update the Tiltfile and various kubernetes files or helm chart values.

_If you need to customization please see the Advanced Usage guide alongside the Genkey Tools._

1. Decide what your host name will be for the reverse proxy will be (e.g. example.com)
2. Generate TLS certs for ingress `./scripts/genkey-reverse-proxy $HOSTNAME_OF_REVERSE_PROXY`
3. Generate service-level certs `./scripts/genkey-apps`
4. (Optional) Generate client certificates `./scripts/genkey-client` for PKI support

##### Genkey Tools

Each genkey script has a brief help which you can access like

- `./scripts/genkey-apps --help`
- `./scripts/genkey-client --help`
- `./scripts/genkey-reverse-proxy --help`
