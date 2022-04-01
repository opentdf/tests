# Cluster E2E tests

[`kuttl`](https://kuttl.dev/) declarative cluster tests live here.

## Install test runner
To install the `kuttl` CLI, [go here](https://kuttl.dev/docs/cli.html)

## Run tests
`kuttl` relies on [`kuttl-test.yaml`](./kuttl-test.yaml) in the folder it's executed from to tell it what tests to run:

- `kubectl kuttl test`

or it can be pointed directly at a test folder, and it can pick up test steps that way:

- `kubectl kuttl test backend/tests/cluster`

## Details
- `kuttl` by default will run tests against whatever Kube cluster your `kubeconfig` currently points at.
- `kuttl` is declarative, not imperative 
  - so our scripts assume that our app has been deployed via Helm before `kubectl kuttl test` is run, and then checks that current cluster state matches what we've defined 
  - you can run setup shell scripts/commands as a 'pre-test' step, but the actual assertion can only be a comparison of yaml snippets against current k8s state
- Since `kuttl` is a declarative state checker, it will wait a configurable amount of time for a cluster to reach the desired state - this is set to 5 mins since a fresh local cluster that needs to pull all images can take a while to reach a ready state.
  - This means you can use `kuttl` as a cluster readiness checker for e.g. pipeline testing/shell scripts - when(if) the tests pass, the cluster is ready.
