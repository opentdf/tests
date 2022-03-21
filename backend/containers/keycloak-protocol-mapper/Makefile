OTDF_IMAGE=opentdf/keycloak
OTDF_VERSION=15.1.1-r10
KEYCLOAK_BASE_VERSION=15.1.1
KEYCLOAK_BASE_IMAGE=ghcr.io/opentdf/keycloak-multiarch-base

# Destroy any previously-created buildx context
.PHONY: docker-buildx-armclean
docker-buildx-armclean:
	docker buildx use default
	docker buildx rm opentdf-keycloak-cross || true

# Clone the Keycloak upstream docker image repo
.PHONY: keycloak-repo-clone
keycloak-repo-clone: docker-buildx-armclean
	rm -rf keycloak-containers
	git clone -b ${KEYCLOAK_BASE_VERSION} https://github.com/keycloak/keycloak-containers.git

# Set up a custom buildx context that supports building a multi-arch image
.PHONY: docker-buildx-armsetup
docker-buildx-armsetup: docker-buildx-armclean
	docker buildx create --name opentdf-keycloak-cross
	docker buildx use opentdf-keycloak-cross
	docker buildx inspect --bootstrap

# Use buildx to build and push an image with amd64 and arm64 compat
# NOTE that this base image has to be pushed to a registry before other images can be built off of it
# because of some buildkite manifest incompatibility stuff
# https://docs.docker.com/engine/reference/commandline/buildx_build/#output
.PHONY: keycloak-base-buildpush
keycloak-base-buildpush: docker-buildx-armsetup keycloak-repo-clone
	cd keycloak-containers/server && \
		docker buildx build --platform linux/arm64,linux/amd64 -t ${KEYCLOAK_BASE_IMAGE}:${KEYCLOAK_BASE_VERSION} --push .

.PHONY: dockerbuild
dockerbuild:
	docker build -t ${OTDF_IMAGE}:${OTDF_VERSION} .

.PHONY: dockerbuildpush
dockerbuildpush: dockerbuild
	docker push ${OTDF_IMAGE}:${OTDF_VERSION}
