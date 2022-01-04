# etheria Tiltfile for development
# reference https://docs.tilt.dev/api.html

# extensions https://github.com/tilt-dev/tilt-extensions
# nice-to-have change from `ext:` to `@tilt_ext`
load("ext://secret", "secret_yaml_generic")
load("ext://helm_remote", "helm_remote")

ALPINE_VERSION = "3.13"
PY_VERSION = "3.9"

# secrets
k8s_yaml(
    secret_yaml_generic(
        "etheria-secrets",
        from_file=[
            "EAS_PRIVATE_KEY=certs/eas-private.pem",
            "EAS_CERTIFICATE=certs/eas-public.pem",
            "KAS_EC_SECP256R1_CERTIFICATE=certs/kas-ec-secp256r1-public.pem",
            "KAS_CERTIFICATE=certs/kas-public.pem",
            "KAS_EC_SECP256R1_PRIVATE_KEY=certs/kas-ec-secp256r1-private.pem",
            "KAS_PRIVATE_KEY=certs/kas-private.pem",
            "ca-cert.pem=certs/ca.crt",
        ],
    )
)
k8s_yaml(
    secret_yaml_generic(
        "attributes-secrets",
        from_literal="POSTGRES_PASSWORD=myPostgresPassword",
    )
)
k8s_yaml(
    secret_yaml_generic(
        "entitlements-secrets", from_literal=["POSTGRES_PASSWORD=myPostgresPassword"]
    )
)
k8s_yaml(
    secret_yaml_generic(
        "tdf-storage-secrets",
        from_literal=[
            "AWS_SECRET_ACCESS_KEY=mySecretAccessKey",
            "AWS_ACCESS_KEY_ID=myAccessKeyId",
        ],
    )
)

# builds
docker_build("opentdf/python-base", context = "containers/python_base",
    build_args = {"ALPINE_VERSION": ALPINE_VERSION, "PY_VERSION": PY_VERSION})
docker_build("opentdf/keycloak", context = "containers/keycloak-protocol-mapper", build_args = {"MAVEN_VERSION": "3.8.4", "JDK_VERSION":"11", "KEYCLOAK_VERSION":"15.0.2"})
docker_build("opentdf/attributes", context = "./containers",
      dockerfile = "./containers/attributes/Dockerfile",
    build_args = {"PY_VERSION": PY_VERSION})
docker_build("opentdf/claims", context = "containers/claims",
    build_args = {"PY_VERSION": PY_VERSION})
docker_build("opentdf/entitlements", context = "./containers",
      dockerfile = "./containers/entitlements/Dockerfile",
    build_args = {"PY_VERSION": PY_VERSION})
docker_build("opentdf/kas", context = "containers/kas",
    build_args = {"PY_VERSION": PY_VERSION})
docker_build("opentdf/storage", context = "containers/storage",
    build_args = {"ALPINE_VERSION": ALPINE_VERSION, "PY_VERSION": PY_VERSION})

# remote resources
# usage https://github.com/tilt-dev/tilt-extensions/tree/master/helm_remote#additional-parameters
helm_remote("keycloak", repo_url="https://codecentric.github.io/helm-charts")
helm_remote(
    "postgresql",
    repo_url="https://charts.bitnami.com/bitnami",
    release_name="tdf",
    values=["deployments/docker-desktop/tdf-postgresql-values.yaml"],
)

# helm charts
# usage https://docs.tilt.dev/helm.html#helm-options
k8s_yaml(
    helm(
        "charts/attributes",
        "attributes",
        values=["deployments/docker-desktop/attributes-values.yaml"],
    )
)
k8s_yaml(
    helm(
        "charts/entitlements",
        "entitlements",
        values=["deployments/docker-desktop/entitlements-values.yaml"],
    )
)
k8s_yaml(
    helm("charts/kas", "kas", values=["deployments/docker-desktop/kas-values.yaml"])
)
# TODO this service requires actual S3 secrets
# TODO or use https://github.com/localstack/localstack
# k8s_yaml(helm('charts/storage', 'storage', values=['deployments/docker-desktop/storage-values.yaml']))
# deprecated
# k8s_yaml(helm('charts/eas', 'eas', values=['deployments/docker-desktop/eas-values.yaml']))

# resource dependencies
k8s_resource("attributes", resource_deps=["tdf-postgresql"])
k8s_resource("entitlements", resource_deps=["tdf-postgresql"])


# TODO: Add a bootstrap job
# docker_build("opentdf/keycloak-bootstrap", context = "containers/keycloak-bootstrap",
#     build_args = {"PY_VERSION": PY_VERSION})
