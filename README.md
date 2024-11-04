# Tests for OpenTDF

## [Cross-client compatibility tests](xtests)

1) `cd xtest`
2) `npm ci && npm i @opentdf/sdk@CLIENT_VERSION`
3) `pip install -r ./requirements.txt`
4) `tilt up`

### To use a Github Package Manager Version

Before doing theabove, [configure Github packages as the scope provider for opentdf](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-npm-registry#authenticating-to-github-packages)

```
npm login --scope=@opentdf --registry=https://npm.pkg.github.com
```

## [Vulnerability](vulnerability)

> Automated checks for vulnerabilities identified during penetration testing

Place to run frontend and backend together locally.
Check Backend "Quick Start and Development" for [Prerequisites](https://github.com/opentdf/backend#prerequisites)

1) delete the cluster with `ctlptl delete cluster kind-kind`
    and clear saved related images in docker
    if you've run integration tests locally from other folder
2) run `ctlptl create cluster kind --registry=ctlptl-registry`
3) `cd vulnerability`
4) `tilt up`

If you are running locally on mac,
frontend 'npm run build' step may take too long.
A possible solution is to run `npm run build`
and change `frontend/Dockerfile` line `RUN npm run build` to `COPY build/ build/`
so it won't run it inside docker.
Be careful not to push these changes,
we won't need that to CI machines that runs on linux.
