# tests
Tests for OpenTDF

## [Vulnerability](vulnerability)

Place to run frontend and backend together locally.
Check Backend "Quick Start and Development" for [Prerequisites](https://github.com/opentdf/backend#prerequisites)

1) To update the 
   <br/>`git submodule update --init --recursive`
   <br/>`git submodule foreach --recursive git fetch`
   <br/>`git submodule foreach git merge origin main`
2) delete `ctlptl delete cluster kind-kind` and clear saved related images in docker if you runned integration tests locally from other folder
3) run `ctlptl create cluster kind --registry=ctlptl-registry`

If you are running locally on mac frontend 'npm run build' step may take too long. Possible solution is run this
command `npm run build` and change frontend/Dockerfile line `RUN npm run build` to `COPY build/ build/` so it won`t
run it inside docker. Be careful not to push this changes, we won't need that to CI machines that runs on linux.

Then

## Cross-client compatibiliy tests (xtests)
1) `cd xtest`
2) `npm ci && npm i @opentdf/client@CLIENT_VERSION`
3) `pip3 install -r ./requirements.txt`
4) `tilt up`

### To use a Github Package Manager Version

Before doing theabove, [configure Github packages as the scope provider for opentdf](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-npm-registry#authenticating-to-github-packages)

```
npm login --scope=@opentdf --registry=https://npm.pkg.github.com
```
