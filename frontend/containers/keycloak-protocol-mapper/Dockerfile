# NOTE - This base image is used here, but it should also really be used in other places such as the e2e test
# NOTE - The version is also needed in the site-packages COPY command below and should be x.x not x.x.x
ARG MAVEN_VERSION=3.8.2
ARG JDK_VERSION=11
ARG KEYCLOAK_BASE_VERSION=15.0.2
ARG CONTAINER_REGISTRY=docker.io
ARG KEYCLOAK_BASE_IMAGE=virtru/keycloak-base #TODO make this `opentdf/keycloak-multiplat-base` once we go public - we are already publishing this base image
    #to `ghcr.io/opentdf` but that is not publicly accessible yet.

FROM maven:${MAVEN_VERSION}-jdk-${JDK_VERSION} as claimsmapperbuild

COPY custom-mapper /usr/src/custom-mapper
RUN mvn -f  /usr/src/custom-mapper/pom.xml clean package

FROM ${CONTAINER_REGISTRY}/${KEYCLOAK_BASE_IMAGE}:${KEYCLOAK_BASE_VERSION}

# Pack this Java mapper binary into the Keycloak container
COPY --from=claimsmapperbuild /usr/src/custom-mapper/target/*.jar /opt/jboss/keycloak/standalone/deployments/
