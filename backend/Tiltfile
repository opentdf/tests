# etheria Tiltfile for development
# reference https://docs.tilt.dev/api.html

# extensions https://github.com/tilt-dev/tilt-extensions
load("ext://helm_remote", "helm_remote")
load("ext://secret", "secret_from_dict", "secret_yaml_generic")
load("ext://min_tilt_version", "min_tilt_version")

min_tilt_version("0.25")

ALPINE_VERSION = os.environ.get("ALPINE_VERSION", "3.15")
PY_VERSION = os.environ.get("PY_VERSION", "3.10")
KEYCLOAK_BASE_VERSION = str(
    local('cut -d- -f1 < "{}"'.format("containers/keycloak-protocol-mapper/VERSION"))
).strip()

# ghcr.io == GitHub packages. pre-release versions, created from recent green `main` commit
# docker.io == Docker hub. Manually released versions
CONTAINER_REGISTRY = os.environ.get("CONTAINER_REGISTRY", "ghcr.io")  # Docker Hub


def from_dotenv(path, key):
    """Read a variable from a `.env` file"""
    return str(local('. "{}" && echo "${}"'.format(path, key))).strip()


# secrets
local("./scripts/genkeys-if-needed")

all_secrets = {
    v: from_dotenv("./certs/.env", v)
    for v in [
        "CA_CERTIFICATE",
        "EAS_CERTIFICATE",
        "KAS_CERTIFICATE",
        "KAS_EC_SECP256R1_CERTIFICATE",
        "KAS_EC_SECP256R1_PRIVATE_KEY",
        "KAS_PRIVATE_KEY",
    ]
}
all_secrets["POSTGRES_PASSWORD"] = "myPostgresPassword"
all_secrets["ca-cert.pem"] = all_secrets["CA_CERTIFICATE"]


def only_secrets_named(*items):
    return {k: all_secrets[k] for k in items}


k8s_yaml(
    secret_from_dict(
        "etheria-secrets",
        inputs=only_secrets_named(
            "POSTGRES_PASSWORD",
            "EAS_CERTIFICATE",
            "KAS_EC_SECP256R1_CERTIFICATE",
            "KAS_CERTIFICATE",
            "KAS_EC_SECP256R1_PRIVATE_KEY",
            "KAS_PRIVATE_KEY",
            "ca-cert.pem",
        ),
    )
)
k8s_yaml(
    secret_from_dict(
        "attributes-secrets",
        inputs=only_secrets_named("POSTGRES_PASSWORD"),
    )
)
k8s_yaml(
    secret_from_dict(
        "entitlements-secrets", inputs=only_secrets_named("POSTGRES_PASSWORD")
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
    CONTAINER_REGISTRY + "/opentdf/keycloak-multiarch-base",
    "containers/keycloak-protocol-mapper/keycloak-containers/server",
    build_args={
        "CONTAINER_REGISTRY": CONTAINER_REGISTRY,
    },
)
docker_build(
    CONTAINER_REGISTRY + "/opentdf/keycloak",
    context="containers/keycloak-protocol-mapper",
    build_args={
        "CONTAINER_REGISTRY": CONTAINER_REGISTRY,
        "KEYCLOAK_BASE_IMAGE": CONTAINER_REGISTRY + "/opentdf/keycloak-multiarch-base",
        "KEYCLOAK_BASE_VERSION": KEYCLOAK_BASE_VERSION,
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
        set=[
            "image.name=" + CONTAINER_REGISTRY + "/opentdf/claims",
            "secretRef.name=etheria-secrets",
        ],
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
#     secret_from_dict(
#         "tdf-storage-secrets",
#         inputs={
#             "AWS_SECRET_ACCESS_KEY": "mySecretAccessKey",
#             "AWS_ACCESS_KEY_ID": "myAccessKeyId",
#         },
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
# k8s_custom_deploy("Manual PVC Delete On Teardown", 'echo ""', "kubectl delete pvc --all", "")
