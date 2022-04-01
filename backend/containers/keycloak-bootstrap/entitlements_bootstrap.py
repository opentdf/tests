import os
import logging
import requests
import yaml
from keycloak import KeycloakAdmin, KeycloakOpenID


logging.basicConfig()
logger = logging.getLogger("keycloak_bootstrap")
logger.setLevel(logging.DEBUG)

# tdf_realm_user_attrmap = {
#     'tdf-user': [
#         "https://example.com/attr/Classification/value/C",
#         "https://example.com/attr/COI/value/PRX"
#     ],
#     'user1': [
#         "https://example.com/attr/Classification/value/S",
#         "https://example.com/attr/COI/value/PRX"
#     ],
#     'bob_1234': [
#         "https://example.com/attr/Classification/value/C",
#         "https://example.com/attr/COI/value/PRC"
#     ],
#     'alice_1234': [
#         "https://example.com/attr/Classification/value/C",
#         "https://example.com/attr/COI/value/PRD"
#     ]
# }

# tdf_realm_client_attrmap = {
#     'tdf-client': [
#         "https://example.com/attr/Classification/value/S",
#         "https://example.com/attr/COI/value/PRX"
#     ],
#     'browsertest': [
#         "https://example.com/attr/Classification/value/C",
#         "https://example.com/attr/COI/value/PRA"
#     ],
#     'service-account-tdf-client': [
#         "https://example.com/attr/Classification/value/C",
#         "https://example.com/attr/COI/value/PRB"
#     ],
#     'client_x509': [
#         "https://example.com/attr/Classification/value/S",
#         "https://example.com/attr/COI/value/PRX"
#     ],
#     'dcr-test': [
#         "https://example.com/attr/Classification/value/C",
#         "https://example.com/attr/COI/value/PRF"
#     ]
# }


def insertAttrsForUsers(keycloak_admin, entitlement_host, user_attr_map, authToken):
    users = keycloak_admin.get_users()
    logger.info(f"Got users: {users}")

    for user in users:
        if user["username"] not in user_attr_map:
            continue
        loc = f"{entitlement_host}/entitlements/{user['id']}"
        attrs = user_attr_map[user["username"]]
        logger.info(
            "Entitling for user: [%s] with [%s] at [%s]", user["username"], attrs, loc
        )
        logger.debug("Using auth JWT: [%s]", authToken)

        for attr in attrs:
            response = requests.post(
                loc,
                json=[attr],
                headers={"Authorization": f"Bearer {authToken}"},
            )
            if response.status_code != 200:
                logger.error(
                    "Unexpected code [%s] from entitlements service when attempting to entitle user! [%s]",
                    response.status_code,
                    response.text,
                    exc_info=True,
                )
                exit(1)


def insertAttrsForClients(keycloak_admin, entitlement_host, client_attr_map, authToken):
    clients = keycloak_admin.get_clients()

    for client in clients:
        if client["clientId"] not in client_attr_map:
            continue
        clientId = client["clientId"]
        loc = f"{entitlement_host}/entitlements/{client['id']}"
        attrs = client_attr_map[clientId]
        logger.info(
            "Entitling for client: [%s] with [%s] at [%s]", clientId, attrs, loc
        )
        logger.debug("Using auth JWT: [%s]", authToken)
        for attr in attrs:
            response = requests.post(
                loc,
                json=[attr],
                headers={"Authorization": f"Bearer {authToken}"},
            )
            if response.status_code != 200:
                logger.error(
                    "Unexpected code [%s] from entitlements service when attempting to entitle client! [%s]",
                    response.status_code,
                    response.text,
                    exc_info=True,
                )
                exit(1)


def insertEntitlementAttrsForRealm(
    keycloak_admin, target_realm, keycloak_auth_url, entity_attrmap
):
    logger.info("Inserting attrs for realm: [%s]", target_realm)
    entitlement_clientid = os.getenv("ENTITLEMENT_CLIENT_ID")
    entitlement_username = os.getenv("ENTITLEMENT_USERNAME")
    entitlement_password = os.getenv("ENTITLEMENT_PASSWORD")
    entitlement_host = os.getenv("ENTITLEMENT_HOST", "http://opentdf-entitlements:4030")

    keycloak_openid = KeycloakOpenID(
        # NOTE: `realm_name` IS NOT == `target_realm` here
        # Target realm is the realm you're querying users from keycloak for
        # `realm_name` is the realm you're using to get a token to talk to entitlements with
        # They are not the same.
        server_url=keycloak_auth_url,
        client_id=entitlement_clientid,
        realm_name="tdf",
    )  # Entitlements endpoint always uses `tdf` realm client creds
    authToken = keycloak_openid.token(entitlement_username, entitlement_password)

    insertAttrsForUsers(
        keycloak_admin, entitlement_host, entity_attrmap, authToken["access_token"]
    )
    insertAttrsForClients(
        keycloak_admin, entitlement_host, entity_attrmap, authToken["access_token"]
    )
    logger.info("Finished inserting attrs for realm: [%s]", target_realm)


def entitlements_bootstrap():
    username = os.getenv("keycloak_admin_username")
    password = os.getenv("keycloak_admin_password")

    keycloak_hostname = os.getenv("keycloak_hostname", "http://localhost:8080")
    keycloak_auth_url = keycloak_hostname + "/auth/"

    keycloak_admin_tdf = KeycloakAdmin(
        server_url=keycloak_auth_url,
        username=username,
        password=password,
        realm_name="tdf",
        user_realm_name="master",
    )

    # Contains a map of `entities` to attributes we want to preload
    # Entities can be clients or users, doesn't matter
    with open("/etc/virtru-config/entitlements.yaml") as f:
        entity_attrmap = yaml.safe_load(f)

    insertEntitlementAttrsForRealm(
        keycloak_admin_tdf, "tdf", keycloak_auth_url, entity_attrmap
    )
    # FIXME: Enable PKI realm
    keycloak_admin_tdf_pki = KeycloakAdmin(
        server_url=keycloak_auth_url,
        username=username,
        password=password,
        realm_name="tdf-pki",
        user_realm_name="master",
    )
    insertEntitlementAttrsForRealm(
        keycloak_admin_tdf_pki, "tdf-pki", keycloak_auth_url, entity_attrmap
    )

    return True
