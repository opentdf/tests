# E2E tests

- The E2E tests in this folder stand up a K8S Job, and use the JS `opentdf/client-web` or `opentdf/client-python` to exercise the backend.

- These tests have been tested locally in `KIND` but should work in any K8S cluster where the `opentdf/backend` OIDC-enabled Helm charts are deployed.

- See [cluster/README.md](./cluster/README.md) for more details about the test runner (kuttl)

#### To run the Tilt based tests
1. Clone this repo (`opentdf/backend`)
1. Install your credentials for the GitHub package repository with `npm login`, following [these instructions](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-npm-registry#authenticating-with-a-personal-access-token). The currently (Q1 2022) method to authenticate is with a PAT (Personal Access Token) with read access to the `opentdf` org, then use it to log in with `npm login --scope=@opentdf --registry=https://npm.pkg.github.com`, entering your GitHub username as the username and your fresh PAT value as the password.
1. Follow [the Tilt Preparation](https://docs.tilt.dev/tutorial/1-prerequisites.html) and configure a local K8S (or remote) cluster, e.g. using Kind and `ctlptl`.
1. `cd backend/tests/integration`
1. `tilt up`

#### To run the KUTTL tests
1. Clone this repo (`opentdf/backend`)
1. Follow `Minikube Quckstart` in `../README-keycloak-idp.md` to deploy Helm charts into Minikube
1. [Install KUTTL](https://kuttl.dev/docs/cli.html)
1. `cd backend/tests/cluster`
1. `kubectl kuttl test`
