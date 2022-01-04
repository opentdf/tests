# Keycloak Identity Provider (IdP)

Keycloak is our Identity Provider (IdP) software.


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


## More Details About Keycloak

Note:  (some of this is historical)

This approach will stand up a Keycloak instance in a test cluster that is configured to serve test tokens
and interact with a KAS instance.

1. Create cluster (e.g. `minikube start`)

1. Set up pull secret for Virtru dockerhub (this lets us fetch our custom Keycloak image):
`kubectl create secret docker-registry regcred --docker-server=https://index.docker.io/v2/ --docker-username=blegget --docker-password=<your token/pw>
--docker-email=bleggett@virtru.com`

From here you can run `deploy-keycloak-minikube.sh` to deploy all the charts to your minikube cluster:

1. Clone [the etheria repo](https://github.com/opentdf/backend) alongside this repo (`keycloak-poc` and `etheria` should be in the same containing directory)
1. run `deploy-keycloak-minikube.sh`

    1. This will use an upstream Helm chart to install Keycloak in HA mode w/Postgres, with our preconfigured KC image.
       You can access locally by using the following commands:

       ``` sh
       export POD_NAME=$(kubectl get pods --namespace default -l "app.kubernetes.io/name=keycloak,app.kubernetes.io/instance=keycloak" -o name)
       echo "Visit http://127.0.0.1:8080 to use your application"
       kubectl --namespace default port-forward "$POD_NAME" 8080
       ```

    1. This will install the Custom Claim attribute mapper (this is a PoC service that supplies Keycloak with custom Virtru claims).

    1. This sets up a demo realm and user in Keycloak we can use for testing (check values.yaml for demo admin creds).

    1. This will stand up a KAS instance using the `eternia` KAS chart.
       You can access this KAS instance locally by using the following commands:

       ``` sh
       export KAS_POD_NAME=$(kubectl get pods --namespace default -l "app.kubernetes.io/name=kas,app.kubernetes.io/instance=kas" -o name)
       echo "Visit http://127.0.0.1:4000 to use your application"
       kubectl --namespace default port-forward "$KAS_POD_NAME" 4000
       ```

1. CLI Client Credential test:

    ``` sh
    export CLIENT_ID=tdf-client
    export CLIENT_SECRET=123-456
    curl -s http://127.0.0.1:8080/auth/realms/tdf/protocol/openid-connect/token -d grant_type=client_credentials -d client_id=$CLIENT_ID -d client_secret=$CLIENT_SECRET --header 'X-VirtruPubKey: 123456'
    ```

## For people working on the repo

There are 3 special bits in this repo you need to care about:

1. Keycloak (we use the upstream container but pack in a custom JAR file)
1. A custom Virtru JAR extension for Keycloak that makes webservice calls, and is invoked by Keycloak during auth flows (see [custom-mapper](custom-mapper)).
1. A Custom Claim attribute provider PoC webservice that supplies claims/attributes, which the Virtru JAR calls (see [custom-claim-test-webservice](custom-claim-test-webservice)).

### Building images

1. Run `build-keycloak.sh` in the parent directory - this will invoke `make dockerbuildpush` for each container we make use of.

### Custom Keycloak image build with custom attribute mapper JAR

We use the upstream Keycloak image and pack a custom JAR file into it - to generate that custom image with the JAR file:
1. `Makefile` - this will compile the `custom-mapper` JAR, pack it in the `keycloak` container, and then you can run it locally via ` docker run -p 8080:8080 opentdf/keycloak:0.0.2` - just rerun `build-image.sh` after making mapper code changes

### Custom Claim attribute provider build/test

See [custom-claim-test-webservice/README.md](custom-claim-test-webservice/README.md)

### Examples of advanced OIDC/Keycloak flows

See [EXAMPLES.md](EXAMPLES.md)
