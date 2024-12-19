# Tests for OpenTDF

## [Cross-client compatibility tests](xtests)

See the [xtest docs](xtest/README.md) for instructions on running the tests.

## [Vulnerability](vulnerability)

> Automated checks for vulnerabilities identified during penetration testing

1) Start up a platform instance following the instructions in the [platform repo](https://github.com/opentdf/platform).
2) `cd vulnerability`
3) `npm ci`
4) `npm run test`
