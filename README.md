# Tests for OpenTDF

> **Fork note:** This is `arkavo-org/opentdf-tests`, a fork of [`opentdf/tests`](https://github.com/opentdf/tests) that adds **community SDK** conformance (Rust, Swift, Python). Official go/java/js paths stay upstream-compatible.

## [Cross-client compatibility tests](xtest)

See the [xtest docs](xtest/README.md) for instructions on running the tests.

### Community SDK Stage-1

See [docs/community-conformance.md](docs/community-conformance.md) and the design [docs/community-xtest-design.md](docs/community-xtest-design.md).

| Workflow | Purpose |
|----------|---------|
| `xtest.yml` | Official go / java / js matrix (unchanged core) |
| `community-xtest.yml` | Community python ↔ go@main Stage-1 (tdf) |

## [Vulnerability](vulnerability)

> Automated checks for vulnerabilities identified during penetration testing

1) Start up a platform instance following the instructions in the [platform repo](https://github.com/opentdf/platform).
2) `cd vulnerability`
3) `npm ci`
4) `npm run test`
