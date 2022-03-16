# tests
Tests for openTDF
[Vulnerability](vulnerability)  

Place to run frontend and backend together locally.
Check Backend "Quick Start and Development" for [Prerequisites](https://github.com/opentdf/backend#prerequisites)

0) To pull latest repos run `.github/scripts/subtree-pull-all.sh`
1) cd xtest
2) delete `ctlptl delete cluster kind-kind` and clear saved related images in docker if you runned integration tests locally from other folder
3) run `ctlptl create cluster kind --registry=ctlptl-registry` 
4) run `tilt up`

If you are running locally on mac frontend 'npm run build' step may take too long. Possible solution is run this
command `npm run build` and change frontend/Dockerfile line `RUN npm run build` to `COPY build/ build/` so it won`t
run it inside docker. Be careful not to push this changes, we won't need that to CI machines that runs on linux. 
