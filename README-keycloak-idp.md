
## Virtru Keycloak/IdP Integration

Keycloak is our Identity Provider (IdP), and integrating
it into Virtru's technology requires the following components:

* `attribute_provider`:  A web service that provides Claims Objects
  to Virtru's Keycloak Protocol Mapper.
* `keycloak-protocol-mapper`:  Virtru's Keycloak Protocol Mapper.
  This is custom Virtru-authored Java code that runs inside Keycloak
  after successful client authentication.  It makes a web service
  call to `attribute_provider` to fetch the Claims Object associated
  with the authenticated client and return it inside the signed JWT.
  * The Keycloak container has Keycloak itself, but also configured
    properly with the appropriate configuration options to support Virtru's
    needs as well as a build of the Virtru Protocol Mapper JAR installed
    in the correct location.
* `keycloak-protocol-mapper/bootstrap`:  This is code that connects to
  Keycloak after it starts up and uses a Python Keycloak REST API library
  to properly configure Keycloak for Virtru's needs.
  * It creates the `tdf` realm.
  * It creates the `tdf-client` realm client.
  * It configures the client to use Virtru Protocol Mapper.
  * It configures Virtru Protocol Mapper itself.

## Local Development Quickstart

This procedure will deploy current existing builds of
Keycloak and all relevant dependencies.

To do this, you will need:
* Docker Desktop:  https://www.docker.com/products/docker-desktop
* kubernetes-cli:  `$ brew install kubernetes-cli`
* A local cluster management, such as minikube or kind. Suggestion: Run `scripts/pre-reqs`
  * Make sure minikube is running:  `$ minikube start`
  * Make sure kind is running:  `$ kind create cluster`

To deploy:
* Run this with your username and credentials:
```
$ kubectl create secret docker-registry regcred \
  --docker-server=https://index.docker.io/v2/ \
  --docker-username=h3virtru \
  --docker-password='...' \
  --docker-email=jgrady@virtru.com
```
* Then run: `$ make local-cluster`
* The last command will take about 4 minutes to complete.
  You might see some errors.  This is normal and due to
  system startup ordering:
  * Keycloak must finsh starting.
  * Then, the `keycloak-bootstrap` job will succeed once it
    can connect to keycloak.
  * Then, KAS startup will succeed because it can connect to
    Keycloak and download the public key configured by `bootstrap`.
  * You can monitor progress with the following command (you may need `$ brew install watch` first):
    * `$ watch kubectl get pods`
* Next, run the following commands to port-forward Keycloak and KAS.
  * Open a terminal window and run this to expose Keycloak on `localhost` port 8080:
     ```
     export POD_NAME=$(kubectl get pods --namespace default -l "app.kubernetes.io/name=keycloak,app.kubernetes.io/instance=keycloak" -o name)
     echo "Visit http://127.0.0.1:8080 to use your application"
     kubectl --namespace default port-forward "$POD_NAME" 8080
     ```   
  * Open another terminal window and run this to expose KAS on `localhost` port 8000:
     ```
     kubectl --namespace default port-forward deployment/kas 8000
     ```
  * At this point you should be able to access the Keycloak admin portal at `http://localhost:8080`
  * The default admin username/password should be defined in https://github.com/opentdf/backend/blob/main/charts/keycloak/values.yaml

## Uninstalling Keycloak et al

To uninstall Keycloak, Attribute Provider, etc. from your cluster, run:

```
$ ./make clean-cluster
```
## Running KUTTL acceptance tests

1. Follow [Local Development Quickstart](#local-development-quickstart)
1. Install [kuttl test runner](https://kuttl.dev/docs/cli.html)
1. `cd tests/cluster`
1. `kubectl kuttl test`

### NodeJS SDK Encrypt/Decrypt

* Check out `eternia`:  `$ git clone git+ssh://git@github.com/virtru/eternia`
* `$ cd eternia/packages/sdk-cli`
* `$ rush build`
* `$ rush test`
* `$ export VIRTRU_OIDC_ENDPOINT=http://127.0.0.1:8080`
* `$ export VIRTRU_SDK_KAS_ENDPOINT=http://127.0.0.1:8000`

A successful encrypt will look like this:

```
jgrady@jgrady sdk-cli % cat plaintext.txt
foo bar baz
```

```
jgrady@jgrady sdk-cli % node ./bin/virtru-sdk encrypt ./plaintext.txt --log-level silly --auth tdf:tdf-client:123-456 > 1234.tdf
info encrypt Running encrypt command
info auth Processing auth params
verb auth Processing an auth string
info auth Building Virtru client {
info auth   organizationName: 'tdf',
info auth   clientId: 'tdf-client',
info auth   clientSecret: '123-456',
info auth   kasEndpoint: 'http://127.0.0.1:8000',
info auth   virtruOIDCEndpoint: 'http://127.0.0.1:8080'
info auth }
info data-in Processing data input
debug data-in Checking if file exists.
silly data-in Found file "./plaintext.txt"
info data-in Using file input
silly policy-params Creating policy builder object
info policy-params Processing policy options
silly policy-params Building policy
silly encrypt Build encrypt params
info encrypt Encrypting data
(node:7168) [DEP0005] DeprecationWarning: Buffer() is deprecated due to security and usability issues. Please use the Buffer.alloc(), Buffer.allocUnsafe(), or Buffer.from() methods instead.
(Use `node --trace-deprecation ...` to show where the warning was created)
info encrypt Handle cyphertext output
debug data-out Handle data out
silly data-out Pipe to stdOut
```

And decrypt:

```
jgrady@jgrady sdk-cli % node ./bin/virtru-sdk decrypt ./1234.tdf --log-level silly --auth tdf:tdf-client:123-456
info decrypt Running decrypt command
info auth Processing auth params
verb auth Processing an auth string
info auth Building Virtru client {
info auth   organizationName: 'tdf',
info auth   clientId: 'tdf-client',
info auth   clientSecret: '123-456',
info auth   kasEndpoint: 'http://127.0.0.1:8000',
info auth   virtruOIDCEndpoint: 'http://127.0.0.1:8080'
info auth }
info data-in Processing data input
debug data-in Checking if file exists.
silly data-in Found file "./1234.tdf"
info data-in Using file input
silly decrypt Build decrypt params.
info decrypt Decrypt data.
info decrypt Handle output.
debug data-out Handle data out
silly data-out Pipe to stdOut
foo bar baz
```

## Building Keycloak Components

The default build targets are Docker containers.

To build `attribute-provider`, `keycloak-protocol-mapper`
and `keycloak-protocol-mapper/bootstrap/` Docker containers, run:

`$ ./build-keycloak.sh`

Once builds succeed and you want to publish the Docker images:

`$ ./build-keycloak.sh --push`

```
jgrady@jgrady etheria % cat build-keycloak.sh
#!/bin/bash -x

set -eo pipefail

for dir in attribute_provider/ \
           keycloak-protocol-mapper/ \
           keycloak-protocol-mapper/bootstrap/ ;
do
  pushd $dir
  if [[ $1 == "--push" ]]; then
    make dockerbuildpush
  else
    make
  fi
  popd
done
```
