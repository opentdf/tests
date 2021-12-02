# Etheria Changelog

This log tracks changes to how development
in etheria happens. For details about package
changes, see the appropriate subfolder.

## [Unreleased]

### Added

- SA-309 Consolidate install scripts, make `minikube` the preferred local install method 
- SA-278 Fetch correct Keycloak Realm from token rather than static config.
- SA-273 Add basic token exchange KUTTL test
- Update Keycloak upstream base image to 13.0.1
- SA-279 Update Keycloak bootstrapper to create browserdemo client config
- SA-285 KUTTL E2E tests for OIDC functionality
- PLAT-994 do not run containers as root, update scripting to produce key files owned by the runtime UIDs
- PLAT-1005, PLAT-1006 Multistage Dockerfile for KAS and EAS to reduce end footprint
- PLAT-634 add latest virtru sdk
- PLAT-549 script that update certs if needed added
- Added python core sdk e2e and stress tests with EAS
- Added a Github action workflow for deploying to Docker images
- Added KAS Dockerfile
- PLAT-518 Docker compose implementation
  - EAS as `/eas`
  - KAS as `/kas`
  - Reverse proxy which maps EAS and KAS
- PLAT-518 add keygen scripts for EAS and KAS and Reverse Proxy
- PLAT-452 EAS_ENTITY_ID_HEADER environment variable
- PLAT-464 Performance test script

### Updated

- Updated EAS Dockerfile. gunicorn configuration, /app WORKDIR
- PLAT-518 Remove old keygen data
- PLAT-518 Remove hardcoded key_stash paths

## [0.0.2] - 2020-04-30

### Added

- Added eas, kas, and xtest subdirectories with initial implementations.
- Added `shfmt` pre-commit script. Install with `./scripts/shfmt --install`.

## [0.0.1] - 2020-04-30

### Added

- Added this CHANGELOG, CODEOWNERS, README and the MIT LICENSE.

<!--
References:
*  [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
* [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security
-->
