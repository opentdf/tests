# tdf3-xtest · [![Build status](https://badge.buildkite.com/b87cfe5ea461f8b0b566eab9b8aa5a4fae6dee834eb3017f57.svg)](https://buildkite.com/virtru/tdf3-xtest)

Cross-platform testing for TDF3 SDKs

## Current Status

| Develop                                                                                                                                                                 | Staging                                                                                                                                                                 | Production                                                                                                                                                                    |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [![Build status](https://badge.buildkite.com/8614fb4d74c9f5e65d800d5f85bd38c2093891b8924f67c486.svg)](https://buildkite.com/virtru/tdf3-xtest-tdf3-integration-develop) | [![Build status](https://badge.buildkite.com/617a9c2ed5e8f0a548685a904406b5f9ae70a6c8ae420c73e0.svg)](https://buildkite.com/virtru/tdf3-xtest-tdf3-integration-staging) | [![Build status](https://badge.buildkite.com/368268206ea72bfec7a8179fc3561ab457cd64b1abb6cf6bd5.svg?branch=master)](https://buildkite.com/virtru/tdf3-xtest-tdf3-integration) |

## Local Testing

From the etheria project root, you can just run:

```
xtest/scripts/test-in-containers
```

This script starts a small docker swarm and configures it by sharing secrets
on a temporary local volume.

For local development, you can do the following:

```
scripts/genkeys-if-needed
. certs/.env
export {EAS,KAS{,_EC_SECP256R1}}_{CERTIFICATE,PRIVATE_KEY}
docker compose -f docker-compose.local.yml up -e EAS_CERTIFICATE,EAS_PRIVATE_KEY,KAS_CERTIFICATE,KAS_PRIVATE_KEY,KAS_EC_SECP256R1_CERTIFICATE,KAS_EC_SECP256R1_PRIVATE_KEY --attach-dependencies etheria.local
python3 test/runner.py --crud --owner Alice_1234 --stage compose --sdks sdk/py/nanotdf/cli.sh
```

## Getting Started

Setup dependencies:

```bash
npm install
```

Setup local environment (LOCAL TARGET ONLY):

- `npm run start`
- Double check the `eas.log` and `kas.log` files to ensure the services are up and running.

Run tests:

```bash
npm run test
```

Append the [stage suffix](package.json) if you want to test a certain stage. For instance, to test dev01:

```bash
npm run test-develop01
```

## Adding SDKs

New SDKs can be dropped into the tests using the following procedure:

1. Add an appropriate setup script to install your package. For node, use npm packages. For python, use pipenv or poetry. For C++, use conan.

2. Create a new subdirectory of `sdk/` for your integration.

3. Add an executable script called `cli.sh` to this new subdirectory. The script should expose `encrypt` and `decrypt` operations implemented using the new SDK. The following interface is requried:

```bash
Usage: ./cli.sh <stage> <encrypt | decrypt> <src-file> <dst-file>
```

4. Append the new subdirectory path to the [test runner](test/runner.py)'s `sdks` list.

## Future work

- Improve readme.
- Trim deps.
- Hook up to saas instead of open source.
- Add tests for browser-based js.
- Add tests for C++.
- Add tests for bindings (python, etc).
- Cross-version compatibility
