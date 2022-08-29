# Tiltfile with helpers for configuring OpenTDF
# reference https://docs.tilt.dev/api.html
# extensions https://github.com/tilt-dev/tilt-extensions
# helm remote usage https://github.com/tilt-dev/tilt-extensions/tree/master/helm_remote#additional-parameters

load("ext://helm_remote", "helm_remote")
load("ext://helm_resource", "helm_resource", "helm_repo")
load("ext://min_tilt_version", "min_tilt_version")

min_tilt_version("0.30")

BACKEND_DIR = os.getcwd()

ALPINE_VERSION = os.environ.get("ALPINE_VERSION", "3.16")
PY_VERSION = os.environ.get("PY_VERSION", "3.10")
KEYCLOAK_BASE_VERSION = str(
    local(
        'cut -d- -f1 < "{}/{}"'.format(
            BACKEND_DIR, "containers/keycloak-protocol-mapper/VERSION"
        )
    )
).strip()

CONTAINER_REGISTRY = os.environ.get("CONTAINER_REGISTRY", "ghcr.io")
POSTGRES_PASSWORD = "myPostgresPassword"
OIDC_CLIENT_SECRET = "myclientsecret"
opaPolicyPullSecret = os.environ.get("CR_PAT")


def from_dotenv(path, key):
    # Read a variable from a `.env` file
    return str(local('. "{}" && echo "${}"'.format(path, key))).strip()


local("./scripts/genkeys-if-needed")

all_secrets = {
    v: from_dotenv("./certs/.env", v)
    for v in [
        "CA_CERTIFICATE",
        "ATTR_AUTHORITY_CERTIFICATE",
        "KAS_CERTIFICATE",
        "KAS_EC_SECP256R1_CERTIFICATE",
        "KAS_EC_SECP256R1_PRIVATE_KEY",
        "KAS_PRIVATE_KEY",
    ]
}


def prefix_list(prefix, list):
    return [x for y in zip([prefix] * len(list), list) for x in y]


def dict_to_equals_list(dict):
    return ["%s=%s" % (k, v) for k, v in dict.items()]


def dict_to_helm_set_list(dict):
    combined = dict_to_equals_list(dict)
    return prefix_list("--set", combined)


# values: list of values files
# set: dictionary of value_name: value pairs
# extra_helm_parameters: only valid when devmode=False; passed to underlying `helm update` command
def backend(values=[], set={}, extra_helm_parameters=[], devmode=False):

    #   o8o
    #   `"'
    #  oooo  ooo. .oo.  .oo.    .oooo.    .oooooooo  .ooooo.   .oooo.o
    #  `888  `888P"Y88bP"Y88b  `P  )88b  888' `88b  d88' `88b d88(  "8
    #   888   888   888   888   .oP"888  888   888  888ooo888 `"Y88b.
    #   888   888   888   888  d8(  888  `88bod8P'  888    .o o.  )88b
    #  o888o o888o o888o o888o `Y888""8o `8oooooo.  `Y8bod8P' 8""888P'
    #                                    d"     YD
    #                                    "Y88888P'
    #

    docker_build(
        CONTAINER_REGISTRY + "/opentdf/python-base",
        context=BACKEND_DIR + "/containers/python_base",
        build_args={
            "ALPINE_VERSION": ALPINE_VERSION,
            "CONTAINER_REGISTRY": CONTAINER_REGISTRY,
            "PY_VERSION": PY_VERSION,
        },
    )

    docker_build(
        CONTAINER_REGISTRY + "/opentdf/keycloak-bootstrap",
        BACKEND_DIR + "/containers/keycloak-bootstrap",
        build_args={
            "CONTAINER_REGISTRY": CONTAINER_REGISTRY,
        },
    )

    docker_build(
        CONTAINER_REGISTRY + "/opentdf/keycloak",
        context=BACKEND_DIR + "/containers/keycloak-protocol-mapper",
        build_args={
            "CONTAINER_REGISTRY": CONTAINER_REGISTRY,
            "KEYCLOAK_BASE_VERSION": KEYCLOAK_BASE_VERSION,
            "MAVEN_VERSION": "3.8.4",
            "JDK_VERSION": "11",
        },
    )

    docker_build(
        CONTAINER_REGISTRY + "/opentdf/entitlement-pdp",
        context=BACKEND_DIR + "/containers/entitlement-pdp",
    )

    docker_build(
        CONTAINER_REGISTRY + "/opentdf/entity-resolution",
        context=BACKEND_DIR + "/containers/entity-resolution",
    )

    docker_build(
        CONTAINER_REGISTRY + "/opentdf/kas",
        build_args={
            "ALPINE_VERSION": ALPINE_VERSION,
            "CONTAINER_REGISTRY": CONTAINER_REGISTRY,
            "PY_VERSION": PY_VERSION,
            "PYTHON_BASE_IMAGE_SELECTOR": "",
        },
        context=BACKEND_DIR + "/containers/kas",
        live_update=[
            sync(BACKEND_DIR + "/containers/kas", "/app"),
            run(
                "cd /app && pip install -r requirements.txt",
                trigger=BACKEND_DIR + "/containers/kas/requirements.txt",
            ),
        ],
    )

    for microservice in ["attributes", "entitlements", "entitlement_store"]:
        image_name = CONTAINER_REGISTRY + "/opentdf/" + microservice
        docker_build(
            image_name,
            build_args={
                "ALPINE_VERSION": ALPINE_VERSION,
                "CONTAINER_REGISTRY": CONTAINER_REGISTRY,
                "PY_VERSION": PY_VERSION,
                "PYTHON_BASE_IMAGE_SELECTOR": "",
            },
            container_args=["--reload"],
            context=BACKEND_DIR + "/containers",
            dockerfile=BACKEND_DIR + "/containers/" + microservice + "/Dockerfile",
            live_update=[
                sync(BACKEND_DIR + "/containers/python_base", "/app/python_base"),
                sync(
                    BACKEND_DIR + "/containers/" + microservice, "/app/" + microservice
                ),
                run(
                    "cd /app/ && pip install -r requirements.txt",
                    trigger=BACKEND_DIR
                    + "/containers/"
                    + microservice
                    + "/requirements.txt",
                ),
            ],
        )
    #     o8o
    #     `"'
    #    oooo  ooo. .oo.    .oooooooo oooo d8b  .ooooo.   .oooo.o  .oooo.o
    #    `888  `888P"Y88b  888' `88b  `888""8P d88' `88b d88(  "8 d88(  "8
    #     888   888   888  888   888   888     888ooo888 `"Y88b.  `"Y88b.
    #     888   888   888  `88bod8P'   888     888    .o o.  )88b o.  )88b
    #    o888o o888o o888o `8oooooo.  d888b    `Y8bod8P' 8""888P' 8""888P'
    #                      d"     YD
    #                      "Y88888P'
    #
    # TODO should integrate with a service mesh and stop deploying our own ingress
    # We need to have big headers for the huge bearer tokens we pass around
    # https://kubernetes.github.io/ingress-nginx/user-guide/nginx-configuration/configmap/

    helm_remote(
        "ingress-nginx",
        repo_url="https://kubernetes.github.io/ingress-nginx",
        set=["controller.config.large-client-header-buffers=20 32k"],
        version="4.2.1",
    )

    k8s_resource("ingress-nginx-controller", port_forwards="65432:80")

    # TODO not sure why this needs to be installed separately, but
    # our ingress config won't work without it.
    k8s_yaml(BACKEND_DIR + "/tests/integration/ingress-class.yaml")

    #                                           o8o
    #                                           `"'
    #   .oooo.o  .ooooo.  oooo d8b oooo    ooo oooo   .ooooo.   .ooooo.   .oooo.o
    #  d88(  "8 d88' `88b `888""8P  `88.  .8'  `888  d88' `"Y8 d88' `88b d88(  "8
    #  `"Y88b.  888ooo888  888       `88..8'    888  888       888ooo888 `"Y88b.
    #  o.  )88b 888    .o  888        `888'     888  888   .o8 888    .o o.  )88b
    #  8""888P' `Y8bod8P' d888b        `8'     o888o `Y8bod8P' `Y8bod8P' 8""888P'
    #
    # usage https://docs.tilt.dev/helm.html#helm-options

    # Unfortunately, due to how Tilt (doesn't) work with Helm (a common refrain),
    # `helm upgrade --dependency-update` doesn't solve the issue like it does with plain Helm.
    # So, do it out of band as a shellout.
    local_resource(
        "helm-dep-update",
        "helm dependency update",
        dir=BACKEND_DIR + "/charts/backend",
    )

    set_values = {
        "entity-resolution.secret.keycloak.clientSecret": "123-456",
        "secrets.opaPolicyPullSecret": opaPolicyPullSecret,
        "secrets.oidcClientSecret": OIDC_CLIENT_SECRET,
        "secrets.postgres.dbPassword": POSTGRES_PASSWORD,
        "kas.envConfig.attrAuthorityCert": all_secrets["ATTR_AUTHORITY_CERTIFICATE"],
        "kas.envConfig.ecCert": all_secrets["KAS_EC_SECP256R1_CERTIFICATE"],
        "kas.envConfig.cert": all_secrets["KAS_CERTIFICATE"],
        "kas.envConfig.ecPrivKey": all_secrets["KAS_EC_SECP256R1_PRIVATE_KEY"],
        "kas.envConfig.privKey": all_secrets["KAS_PRIVATE_KEY"],
    }
    set_values.update(set)

    if devmode:
        # NOTE: Run `helm dep update` outside of tilt, as there isn't a good
        # way to make it happen earlier.
        k8s_yaml(
            helm(
                BACKEND_DIR + "/charts/backend",
                name="backend",
                set=dict_to_equals_list(set_values),
                values=values,
            ),
        )
    else:
        # FIXME: I've had to add the `--wait` option, so the helm apply command
        # takes longer than the default timeout for any apply command of 30s.
        # This fixes an issue where the dependant resources (e.g. xtest) run
        # immediately after the apply command, causing race conditions with their
        # configurator scripts and the built-in bootstrap script.
        # Hopefully, either tilt or the helm_resource extension will be improved
        # to avoid this change (or maybe everything will just get faster)
        update_settings(k8s_upsert_timeout_secs=1200)
        helm_resource(
            name="backend",
            chart=BACKEND_DIR + "/charts/backend",
            image_deps=[
                CONTAINER_REGISTRY + "/opentdf/keycloak-bootstrap",
                CONTAINER_REGISTRY + "/opentdf/keycloak",
                CONTAINER_REGISTRY + "/opentdf/attributes",
                CONTAINER_REGISTRY + "/opentdf/entitlements",
                CONTAINER_REGISTRY + "/opentdf/entitlement_store",
                CONTAINER_REGISTRY + "/opentdf/entitlement-pdp",
                CONTAINER_REGISTRY + "/opentdf/entity-resolution",
                CONTAINER_REGISTRY + "/opentdf/kas",
            ],
            image_keys=[
                ("keycloak-bootstrap.image.repo", "keycloak-bootstrap.image.tag"),
                ("keycloak.image.repository", "keycloak.image.tag"),
                ("attributes.image.repo", "attributes.image.tag"),
                ("entitlements.image.repo", "entitlements.image.tag"),
                ("entitlement_store.image.repo", "entitlement_store.image.tag"),
                ("entitlement-pdp.image.repo", "entitlement-pdp.image.tag"),
                ("entity-resolution.image.repo", "entity-resolution.image.tag"),
                ("kas.image.repo", "kas.image.tag"),
            ],
            flags=[
                "--wait",
                "--dependency-update",
            ]
            + dict_to_helm_set_list(set_values)
            + prefix_list("-f", values),
            labels="opentdf",
            resource_deps=["helm-dep-update", "ingress-nginx-controller"],
        )
