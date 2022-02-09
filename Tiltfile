# etheria Tiltfile for development
# reference https://docs.tilt.dev/api.html

# extensions https://github.com/tilt-dev/tilt-extensions
# nice-to-have change from `ext:` to `@tilt_ext`
load("ext://secret", "secret_yaml_generic")
load("ext://helm_remote", "helm_remote")

ALPINE_VERSION = "3.15"
PY_VERSION = "3.10"
# ghcr.io == GitHub packages
CONTAINER_REGISTRY = "docker.io" # Docker Hub

# secrets
local("./scripts/genkeys-if-needed")

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
        from_literal="POSTGRES_PASSWORD=myPostgresPassword",
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

# builds
docker_build(
    CONTAINER_REGISTRY + "/opentdf/python-base",
    context="containers/python_base",
    build_args={
        "ALPINE_VERSION": ALPINE_VERSION,
        "CONTAINER_REGISTRY": CONTAINER_REGISTRY,
        "PY_VERSION": PY_VERSION,
    },
)
docker_build(
    CONTAINER_REGISTRY + "/opentdf/keycloak",
    context="containers/keycloak-protocol-mapper",
    build_args={
        "CONTAINER_REGISTRY": "docker.io",
        "KEYCLOAK_BASE_IMAGE": "virtru/keycloak-base", #TODO fix this after going public
        "KEYCLOAK_BASE_VERSION": "15.0.2",
        "MAVEN_VERSION": "3.8.4",
        "JDK_VERSION": "11",
    },
)
docker_build(
    CONTAINER_REGISTRY + "/opentdf/attributes",
    context="./containers",
    dockerfile="./containers/attributes/Dockerfile",
    build_args={
        "ALPINE_VERSION": ALPINE_VERSION,
        "CONTAINER_REGISTRY": CONTAINER_REGISTRY,
        "PY_VERSION": PY_VERSION,
        "PYTHON_BASE_IMAGE_SELECTOR": "",
    },
)
docker_build(
    CONTAINER_REGISTRY + "/opentdf/claims",
    context="containers",
    dockerfile="./containers/claims/Dockerfile",
    build_args={
        "ALPINE_VERSION": ALPINE_VERSION,
        "CONTAINER_REGISTRY": CONTAINER_REGISTRY,
        "PY_VERSION": PY_VERSION,
        "PYTHON_BASE_IMAGE_SELECTOR": "",
    },
)
docker_build(
    CONTAINER_REGISTRY + "/opentdf/entitlements",
    context="./containers",
    dockerfile="./containers/entitlements/Dockerfile",
    build_args={
        "ALPINE_VERSION": ALPINE_VERSION,
        "CONTAINER_REGISTRY": CONTAINER_REGISTRY,
        "PY_VERSION": PY_VERSION,
        "PYTHON_BASE_IMAGE_SELECTOR": "",
    },
)
docker_build(
    CONTAINER_REGISTRY + "/opentdf/kas",
    context="containers/kas",
    build_args={
        "ALPINE_VERSION": ALPINE_VERSION,
        "CONTAINER_REGISTRY": CONTAINER_REGISTRY,
        "PY_VERSION": PY_VERSION,
        "PYTHON_BASE_IMAGE_SELECTOR": "",
    },
)

# remote resources
# usage https://github.com/tilt-dev/tilt-extensions/tree/master/helm_remote#additional-parameters
helm_remote(
    "keycloak",
    version="17.0.1",
    repo_url="https://codecentric.github.io/helm-charts",
    values=["deployments/docker-desktop/keycloak-values.yaml"],
)
helm_remote(
    "postgresql",
    repo_url="https://charts.bitnami.com/bitnami",
    release_name="tdf",
    version="10.16.2",
    values=["deployments/docker-desktop/tdf-postgresql-values.yaml"],
)

# helm charts
# usage https://docs.tilt.dev/helm.html#helm-options
k8s_yaml(
    helm(
        "charts/attributes",
        "attributes",
        set=["image.name=" + CONTAINER_REGISTRY + "/opentdf/attributes"],
        values=["deployments/docker-desktop/attributes-values.yaml"],
    )
)
k8s_yaml(
    helm(
        "charts/claims",
        "claims",
        set=["image.name=" + CONTAINER_REGISTRY + "/opentdf/claims", "secretRef.name=etheria-secrets"],
        values=["deployments/docker-desktop/claims-values.yaml"],
    )
)
k8s_yaml(
    helm(
        "charts/entitlements",
        "entitlements",
        set=["image.name=" + CONTAINER_REGISTRY + "/opentdf/entitlements"],
        values=["deployments/docker-desktop/entitlements-values.yaml"],
    )
)
k8s_yaml(
    helm(
        "charts/kas",
        "kas",
        set=["image.name=" + CONTAINER_REGISTRY + "/opentdf/kas"],
        values=["deployments/docker-desktop/kas-values.yaml"],
    )
)
# TODO this service requires actual S3 secrets
# TODO or use https://github.com/localstack/localstack
# k8s_yaml(
#     secret_yaml_generic(
#         "tdf-storage-secrets",
#         from_literal=[
#             "AWS_SECRET_ACCESS_KEY=mySecretAccessKey",
#             "AWS_ACCESS_KEY_ID=myAccessKeyId",
#         ],
#     )
# )
# docker_build(
#     CONTAINER_REGISTRY + "/opentdf/storage",
#     context="containers/storage",
#     build_args={
#         "ALPINE_VERSION": ALPINE_VERSION,
#         "CONTAINER_REGISTRY": CONTAINER_REGISTRY,
#         "PY_VERSION": PY_VERSION,
#         "PYTHON_BASE_IMAGE_SELECTOR": "",
#     },
# )
# k8s_yaml(helm('charts/storage', 'storage', values=['deployments/docker-desktop/storage-values.yaml']))
# deprecated
# k8s_yaml(helm('charts/eas', 'eas', values=['deployments/docker-desktop/eas-values.yaml']))

# resource dependencies
k8s_resource("attributes", resource_deps=["tdf-postgresql"])
k8s_resource("entitlements", resource_deps=["tdf-postgresql"])


# TODO: Add a bootstrap job
# docker_build(CONTAINER_REGISTRY + "/opentdf/keycloak-bootstrap", context = "containers/keycloak-bootstrap",
#     build_args = {"PY_VERSION": PY_VERSION})

# The Postgres chart by default does not remove its Persistent Volume Claims: https://github.com/bitnami/charts/tree/master/bitnami/postgresql#uninstalling-the-chart
# This means `tilt down && tilt up` will leave behind old PGSQL databases and volumes, causing weirdness.
# Doing a `tilt down && kubectl delete pvc --all` will solve this
# Tried to automate that teardown postcommand here with Tilt, and it works for everything but `tilt ci` which keeps
# waiting for the no-op `apply_cmd` to stream logs as a K8S resource.
# I have not figured out a clean way to run `down commands` with tilt
#k8s_custom_deploy("Manual PVC Delete On Teardown", 'echo ""', "kubectl delete pvc --all", "")
