IMAGE=virtru/tdf-keycloak
VERSION=15.0.2

all: build

.PHONY: build
build:
	docker build -t ${IMAGE}:${VERSION} .

.PHONY: dockerbuildpush
dockerbuildpush: build
	docker push ${IMAGE}:${VERSION}
