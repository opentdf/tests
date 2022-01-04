# NOTE - This base image is used here, but it should also really be used in other places such as the e2e test
# NOTE - The version is also needed in the site-packages COPY command below and should be x.x not x.x.x
ARG MAVEN_VERSION=3.8.2
ARG JDK_VERSION=11
ARG KEYCLOAK_VERSION=15.0.2

FROM maven:${MAVEN_VERSION}-jdk-${JDK_VERSION} as build

COPY custom-mapper /usr/src/custom-mapper
RUN mvn -f  /usr/src/custom-mapper/pom.xml clean package


FROM quay.io/keycloak/keycloak:${KEYCLOAK_VERSION} as standard

# TODO(PLAT-XXX) Use more standard image
# We have to build this to work on arm64 (2020+ macos)
# https://github.com/keycloak/keycloak-containers/issues/341

# Code below derived from the linked image above, as seen here:
# https://github.com/keycloak/keycloak-containers/blob/main/server/Dockerfile
FROM registry.access.redhat.com/ubi8-minimal

ARG KEYCLOAK_VERSION=15.0.2

ENV KEYCLOAK_VERSION ${KEYCLOAK_VERSION}
ENV JDBC_POSTGRES_VERSION 42.2.5
ENV JDBC_MYSQL_VERSION 8.0.22
ENV JDBC_MARIADB_VERSION 2.5.4
ENV JDBC_MSSQL_VERSION 8.2.2.jre11

ENV LAUNCH_JBOSS_IN_BACKGROUND 1
ENV PROXY_ADDRESS_FORWARDING false
ENV JBOSS_HOME /opt/jboss/keycloak
ENV LANG en_US.UTF-8

ARG GIT_REPO
ARG GIT_BRANCH
ARG KEYCLOAK_DIST=https://github.com/keycloak/keycloak/releases/download/$KEYCLOAK_VERSION/keycloak-$KEYCLOAK_VERSION.tar.gz

USER root

RUN microdnf update -y && microdnf install -y glibc-langpack-en gzip hostname java-11-openjdk-headless openssl tar which && microdnf clean all

COPY --from=standard /opt/jboss/tools /opt/jboss/tools
RUN /opt/jboss/tools/build-keycloak.sh

USER 1000

EXPOSE 8080
EXPOSE 8443

ENTRYPOINT [ "/opt/jboss/tools/docker-entrypoint.sh" ]

CMD ["-b", "0.0.0.0"]

COPY --from=build /usr/src/custom-mapper/target/*.jar /opt/jboss/keycloak/standalone/deployments/
ENV JAVA_OPTS_APPEND="-Dkeycloak.profile=preview -Dkeycloak.profile.feature.token_exchange=enabled"
