all: dockerbuild

COMPONENT_NAME=bootstrap
COMPONENT_NAME_SNAKE=bootstrap
IMAGE=virtru/keycloak-bootstrap
VERSION=0.4.2
VENV_DIR=.venv
PIPENV_VENV_IN_PROJECT=enabled

.PHONY: localbuild
localbuild: lint
	mkdir -p ${VENV_DIR}
	pipenv install

.PHONY: dockerbuild
dockerbuild:
	docker build -t ${IMAGE}:${VERSION} .

.PHONY: dockerbuildpush
dockerbuildpush: dockerbuild
	docker push ${IMAGE}:${VERSION}

.PHONY: run
run:
	pipenv run ./bootstrap.py

.PHONY: testenv
testenv:
	pipenv install --dev

.PHONY: test
test:
	pipenv run pytest --cov-config=.coveragerc --cov=. \
	  --cov-report=term-missing
	  
.PHONY: lint
lint: testenv
	pipenv run pylint bootstrap.py

.PHONY: dockertestenv
dockertestenv:
	pipenv --rm || true
	pipenv install --dev
	pipenv run pytest --cov-config=.coveragerc --cov=. \
	  --cov-report=term-missing
	pipenv --rm || true

.PHONY: clean
clean:
	rm -rf __pycache__ dist/ build/ \
	  src/${COMPONENT_NAME_SNAKE}.egg-info

.PHONY: venvclean
venvclean:
	pipenv --rm || true

