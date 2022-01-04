
## openTDF + Keycloak Identity Provider Integration

Keycloak is our Identity Provider (IdP), and integrating
it into Virtru's technology requires the following components:

* `claims`:  A web service that provides Claims Objects to the openTDF Keycloak
  Protocol Mapper.
* `keycloak-protocol-mapper`:  Virtru's Keycloak Protocol Mapper.
  This is a customized Keycloak image that makes a web service
  call to `claims` to fetch the authorization (authZ) information
  with the authenticated client and return it inside the signed JWT.
* `keycloak-bootstrap`:  A containerized script to initialize the Keycloak
  for use with a demo environment. It can be used as a reference for developing
  code that interacts with Keycloak and the various attribution services within
  the openTDF backend. The demo implementation:
  * creates the `tdf` realm
  * creates the `tdf-client` client (non-person entity -- a service account)
  * configures the client to use Virtru Protocol Mapper
  * configures Virtru Protocol Mapper itself
  * uses the `attributes` service to define some demo attributes
  * uses the `entitlements` service to assign demo attributes to these users

## Local Development Quickstart (macos)

This procedure will deploy current existing builds of
Keycloak and all relevant dependencies.

To do this, you will need:

* Docker Desktop:  https://www.docker.com/products/docker-desktop
* A local cluster cluster and cluster management tools. Suggestion: Run `scripts/pre-reqs`


Running: 

* First, start your local cluster:
  * To start minikube:  `$ minikube start`
  * To start kind:  `$ kind create cluster`
  * To start kind with `ctlptl`: `ctlptl create cluster kind --registry=ctlptl-registry`
* Then run: `tilt up`

### Uninstalling Keycloak et al

To uninstall Keycloak, Attribute Provider, etc. from your cluster, run:

```
$ tilt down
```
### NodeJS SDK Encrypt/Decrypt

* Check out and build `opentdf/client-web`
```
git clone git+ssh://git@github.com/opentdf/client-web`
cd client-web
nvm use
make all && make test
```

A successful encrypt will look like this:

```
echo "Hello openTDF" >plaintext.txt

cli/bin/opentdf.mjs encrypt \
  --kasEndpoint http://localhost:65432/kas \
  --oidcEndpoint http://localhost:65432/keycloak \
  --auth tdf:tdf-client:123-456 \
  --attributes http://opentdf-kas/attr/default/value/default \
  --output sample.tdf \
  plaintext.txt

cli/bin/opentdf.mjs \
  --kasEndpoint http://localhost:65432/kas \
  --oidcEndpoint http://localhost:65432/keycloak \
  --auth tdf:tdf-client:123-456 \
  decrypt sample.tdf
```
