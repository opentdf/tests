IMAGE=virtru/keycloak-poc
VERSION=0.3.5

all: build

.PHONY: build
build:
	docker build -t ${IMAGE}:${VERSION} .

.PHONY: dockerbuildpush
dockerbuildpush: build
	docker push ${IMAGE}:${VERSION}
