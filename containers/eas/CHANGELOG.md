# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [Unreleased]: https://github.com/virtru/tdf3-aa/compare/master...HEAD

PLAT-453, make pki work with front end sdk: ([#50](https://github.com/opentdf/backend/pull/50)): _minor_

- NGINX_HOST should be local.virtru.com (its our convention for local host)
- userId shouldnt be required, otherwise its inconsistent to accounts "defacto reference" implementation
- EAS_ENTITY_ID_HEADER should be taken from env var, not config file

## [0.1.0] - 2019-05-23

WS-9100-sync-masters: ([#67](https://github.com/virtru/tdf3-aa/pull/65)): _minor_

- Added isDefault as an attribute option
- Added default attribute to every EntityObject
- Added attribute create and retrieve endpoints
