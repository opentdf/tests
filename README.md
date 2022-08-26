# tests
Tests for OpenTDF

[Vulnerability](vulnerability)

Place to run frontend and backend together locally.
Check Backend "Quick Start and Development" for [Prerequisites](https://github.com/opentdf/backend#prerequisites)

1) To pull latest repos run
   <br/>`git submodule update --init --recursive`
   <br/>`git submodule foreach --recursive git fetch`
   <br/>`git submodule foreach git merge origin main`
2) delete `ctlptl delete cluster kind-kind` and clear saved related images in docker if you runned integration tests locally from other folder
3) run `ctlptl create cluster kind --registry=ctlptl-registry`

If you are running locally on mac frontend 'npm run build' step may take too long. Possible solution is run this
command `npm run build` and change frontend/Dockerfile line `RUN npm run build` to `COPY build/ build/` so it won`t
run it inside docker. Be careful not to push this changes, we won't need that to CI machines that runs on linux.

Then

## For xtests local setup:
0) `cd projects/client-web`
1) `nvm use; make all`
2) `cd ../../xtest`
3) `npm ci && npm i <../projects/client-web/lib/opentdf-client-*.tgz`
4) `pip3 install -r ./requirements.txt`
5) `tilt up integration-test -- --to-edit opentdf-abacus`
