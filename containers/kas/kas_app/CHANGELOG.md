# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [Unreleased]: https://github.com/virtru/tdf-kas-virtru/compare/master...HEAD

## Added

- PLAT-1030: ([#314](https://github.com/virtru/etheria/pull/314)): _minor_
  - For KAS, setting the EO_BLOCK_LIST or EO_ALLOW_LIST env vars now allows
    immediate 403s for uninterested parties based on user_id (email or DN, 
    usually)
  - To block a specific user, set the value to a comma-separated (no whitespace)
    list, e.g. `export EO_BLOCK_LIST=bob@a.com,alice@b.org`.
  - To allow just one user, set `EO_ALLOW_LIST=me@virtru.com`, for example
  - Blocks are tested before allow list, so don't use * on the block list if
    you are also using an allow list. Instead, the presence of a nonempty
    EO_ALLOW_LIST implies that all non-matching userids are disallowed.

## [0.2.1] - 2019-06-24
### Changed
WS-9083: ([#18](https://github.com/virtru/tdf3-kas-oss/pull/18)): _minor_
  - Uses new loggers
  - tdf3_kas_core dependency increased to v0.4.0-alpha


## [0.2.0] - 2019-05-24
### Changed
WS-9100-use-tag: ([#15](https://github.com/virtru/tdf3-kas-oss/pull/15)): _minor_
  - Same Dockerfile used in both local and pipelines
  - Dependencies have a single-point-of-reference in setup.py
  - Default tdf3_kas_core branch is defined in a file (currently v0.3.2-alpha)

## [0.1.1] - 2019-05-24
### Changed

WS-9100: ([#14](https://github.com/virtru/tdf3-kas-oss/pull/14)): _minor_
  - Bumped CHANGELOG.md to tag this version.

WS-9100: ([#13](https://github.com/virtru/tdf3-kas-oss/pull/13)): _minor_

  - Updated README.md
  - Updated default attribute config
  - Added VERSION and CHANGELOG.md
  - Added logging
  - Moved scripts
