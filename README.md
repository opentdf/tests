# tests
Tests for openTDF

[Vulnerability](vulnerability)

Place to run frontend and backend together locally.
Check Backend "Quick Start and Development" for [Prerequisites](https://github.com/opentdf/backend#prerequisites)


1) cd e2e
2) run `ctlptl create cluster kind --registry=ctlptl-registry`
3) run `tilt up`

You can alter [tilt file](e2e/Tiltfile) to change source of containers. For example:
```
docker_build(
    "ghcr.io/opentdf/abacus",
    local_path("../", "frontend",), // you can change local path to your frontend build
)
```
