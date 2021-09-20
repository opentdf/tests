all: dockerbuild

COMPONENT_NAME=attribute_provider
IMAGE=virtru/claim-test-webservice
VERSION=0.2.4
VENV_DIR=.venv
PIPENV_VENV_IN_PROJECT=enabled

.PHONY: localbuild
localbuild:
	mkdir -p ${VENV_DIR}
	pipenv install -e .

.PHONY: dockerbuild
dockerbuild:
	docker build -t ${IMAGE}:${VERSION} .

.PHONY: dockerbuildpush
dockerbuildpush: dockerbuild
	docker push ${IMAGE}:${VERSION}

.PHONY: run
run:
	./run.sh

.PHONY: testenv
testenv:
	pipenv install --dev -e .

.PHONY: test
test:
	pipenv run pytest --cov=src --cov-report=term-missing tests/

.PHONY: dockertestenv
dockertestenv:
	pipenv --rm || true
	pipenv install --dev -e .
	pipenv run pytest --cov=src --cov-report=term-missing tests/
	pipenv --rm || true

.PHONY: clean
clean:
	rm -rf __pycache__ dist/ build/ \
	  src/${COMPONENT_NAME}.egg-info

.PHONY: venvclean
venvclean:
	pipenv --rm || true

