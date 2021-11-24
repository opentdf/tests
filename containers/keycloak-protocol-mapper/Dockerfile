# NOTE - This base image is used here, but it should also really be used in other places such as the e2e test
# NOTE - The version is also needed in the site-packages COPY command below and should be x.x not x.x.x
ARG MAVEN_VERSION=3.8.2
ARG JDK_VERSION=11
ARG KEYCLOAK_VERSION=15.0.2

FROM maven:${MAVEN_VERSION}-jdk-${JDK_VERSION} as build

COPY custom-mapper /usr/src/custom-mapper
RUN mvn -f /usr/src/custom-mapper/pom.xml clean package

FROM quay.io/keycloak/keycloak:${KEYCLOAK_VERSION}

COPY --from=build /usr/src/custom-mapper/target/*.jar /opt/jboss/keycloak/standalone/deployments/
ENV JAVA_OPTS_APPEND="-Dkeycloak.profile=preview -Dkeycloak.profile.feature.token_exchange=enabled"
