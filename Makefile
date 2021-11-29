.DEFAULT_GOAL := all-containers

.PHONY: all clean-cluster local-cluster all-containers python-base

all: local-cluster

local-cluster: all-containers
	deployments/local/start.sh

all-containers: python-base docker-compose.build.yml $(shell IFS=$'\n' find containers -not -path '*/node_modules/*')
	docker-compose -f docker-compose.build.yml build

python-base: docker-compose.build.yml $(shell find containers/python_base)
	docker-compose -f docker-compose.build.yml build python-base

clean-cluster:
	helm uninstall attribute-provider
	helm uninstall kas
	helm uninstall keycloak
	helm uninstall keycloak-bootstrap
	kubectl delete secret etheria-secrets
