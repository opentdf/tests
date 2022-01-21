# Protected Data Format Reference Services · [![CI](https://github.com/opentdf/backend/actions/workflows/build.yml/badge.svg)](https://github.com/opentdf/backend/actions?query=event%3Apush+branch%3Amain)


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

## Quick Start and Development

This quick start guide is primarily for development and testing the EAS and KAS infrastructure. See [Production](#production) for details on running in production.

### Prerequisites

- Install [Docker](https://www.docker.com/)
    - see https://docs.docker.com/get-docker/

- Install [kubectl](https://kubernetes.io/docs/reference/kubectl/overview/)
    - On macOS via Homebrew: `brew install kubectl`
    - Others see https://kubernetes.io/docs/tasks/tools/

- Install minikube
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
./scripts/pre-reqs docker helm tilt kind octant
```

### Generate local certs in certs/ directory
./scripts/genkeys-if-needed

### Create cluster

```shell
ctlptl create cluster kind --registry=ctlptl-registry --name kind-opentdf
```

### Start cluster

```shell
tilt up
```
 
# Hit spacebar to open web UI

### Cleanup

```shell
tilt down
kind delete cluster --name kind-opentdf
helm repo remove keycloak
```

> (Optional) Run `octant` -> This will open a browser window giving you an overview of your local cluster.

### PR builds

When you open a GitHub PR, an Argo job will run which will publish all openTDF Backend Service images and Helm charts to Virtru's image/chart
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

Or, if you wanted to install all of the openTDF services, you could fetch the top-level chart (which will have all subcharts and images updated to the current PR branch's SHA)

`helm pull virtru/etheria --version 0.1.1-rc-b616e2f --devel`

## Installation in Isolated Kubernetes Clusters

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

KAS and EAS servers support Swagger UI to provide documentation and easier interaction for the REST API.  
Add "/ui" to the base URL of the appropriate server. For example, `http://127.0.0.1:4010/ui/`.
KAS and EAS each have separate REST APIs that together with the SDK support the full TDF3 process for encryption,
authorization, and decryption.

Swagger-UI can be disabled through the SWAGGER_UI environment variable. See the configuration sections of the
README documentation for [KAS](kas_app/README.md) and [EAS](eas/README.md) in this repository.

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

### Cluster tests

Our E2E cluster tests use [kuttl](https://kuttl.dev/docs/cli.html#setup-the-kuttl-kubectl-plugin), and you can run them
against an instance of these services deployed to a cluster (local minikube, or remote)

1. Install these services to a Kubernetes cluster (using the quickstart method above, for example)
1. Install [kuttl](https://kuttl.dev/docs/cli.html#setup-the-kuttl-kubectl-plugin)
1. From the repo root, run `kubectl kuttl test tests/cluster`
1. For advanced usage and more details, refer to [tests/cluster/README.md](tests/cluster/README.md)

> The backend's CI is not currently cluster based, and so the kuttl tests are not being run via CI - this should be corrected when the CI is moved to K8S/Argo.


#### Security test

Once a cluster is running, run `security-test/helm-test.sh`
### Integration Tests

TK

## Deployment

TBD - The backend deployment will be done to Kubernetes clusters via Helm chart.
TBD - for an idea of what's involved in this, including what Helm charts are required, [check the local install script](~/Source/etheria/deployments/local/start.sh)


# Customizing your local development experience
#### Quick Start

To assist in quickly starting use the `./scripts/genkeys-if-needed` to build all the keys. The hostname will be assigned `etheria.local`.
Make sure to add `127.0.0.1           etheria.local` to your `/etc/hosts` or `c:\windows\system32\drivers\etc\hosts`.

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
