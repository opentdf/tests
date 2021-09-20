# E2E tests

- The E2E tests in this folder stand up a K8S Job, and use the JS `sdk-cli` from `eternia` to exercise the TDF3 SDK against
KAS/Keycloak/etc instances running in the same cluster.

- These tests have been tested locally in `minikube` but should work in any K8S cluster where the `etheria` OIDC-enabled Helm charts are deployed.

- See [cluster/README.md](./cluster/README.md) for more details about the test runner (kuttl)

#### To run the tests
1. Clone this repo (`etheria`)
1. Follow `Minikube Quckstart` in `etheria/README-keycloak-idp.md` to deploy Etheria Helm charts into Minikube
1. [Install KUTTL](https://kuttl.dev/docs/cli.html)
1. `cd etheria/tests/cluster`
1. `kubectl kuttl test`

#### To update the `eternia` test runner image (TODO we can drop all this when OIDC-enabled `sdk-cli` is published to public NPM)
1. Clone this repo (`etheria`)
1. Clone the `eternia` alongside `etheria`
1. `cd etheria/tests/containers/eternia-kuttl-runner`
1. `build-test-runner-image.sh`
