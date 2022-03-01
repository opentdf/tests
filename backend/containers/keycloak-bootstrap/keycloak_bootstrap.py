import os
import json
import logging
from keycloak import KeycloakAdmin

URL_ADMIN_AUTHENTICATOR_EXECUTION_CONFIG = (
    "admin/realms/{realm-name}/authentication/executions/{flow-id}/config"
)
# We need to do this manually because KeycloakAdmin expects a 204 response and sometimes we get a valid 202.  :/
URL_ADMIN_EXECUTION_FLOW = (
    "admin/realms/{realm-name}/authentication/flows/{flow-alias}/executions"
)

logging.basicConfig()
logger = logging.getLogger("keycloak_bootstrap")
logger.setLevel(logging.DEBUG)


def check_matched(pattern, allData):
    filtered_item = [
        d for d in allData if all((k in d and d[k] == v) for k, v in pattern.items())
    ]
    if filtered_item is not None:
        return filtered_item
    return []


def createUsersInRealm(keycloak_admin):
    for username in ("Alice_1234", "Bob_1234"):
        try:
            new_user = keycloak_admin.create_user(
                {"username": username, "enabled": True}
            )
            logger.info("Created new user %s", new_user)
        except Exception as e:
            logger.warning("Could not create user %s!", username)
            logger.warning(str(e))
    passwordedUsers = os.getenv(
        "passwordUsers", "testuser@virtru.com,user1,user2"
    ).split(",")
    for passwordedUser in passwordedUsers:
        try:
            new_user = keycloak_admin.create_user(
                {
                    "username": passwordedUser,
                    "enabled": True,
                    "credentials": [
                        {
                            "value": "testuser123",
                            "type": "password",
                        }
                    ],
                }
            )
            logger.info("Created new passworded user %s", new_user)

            # Add Abacus-related roles to user
            assignViewRolesToUser(keycloak_admin, new_user)
        except Exception as e:
            logger.warning("Could not create passworded user %s!", username)
            logger.warning(str(e))


def addVirtruClientAudienceMapper(keycloak_admin, keycloak_client_id, client_audience):
    logger.info("Assigning client audience mapper to client %s", keycloak_client_id)
    try:
        keycloak_admin.add_mapper_to_client(
            keycloak_client_id,
            payload={
                "protocol": "openid-connect",
                "config": {
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                    "included.custom.audience": client_audience,
                },
                "name": f"Virtru {client_audience} Audience Mapper",
                "protocolMapper": "oidc-audience-mapper",
            },
        )
    except Exception as e:
        logger.warning(
            "Could not add client audience mapper to client %s - this likely means it is already there, so we can ignore this.",
            keycloak_client_id,
        )
        logger.warning(
            "Unfortunately python-keycloak doesn't seem to have a 'remove-mapper' function"
        )
        logger.warning(str(e))


def addVirtruMappers(keycloak_admin, keycloak_client_id):
    logger.info("Assigning custom mappers to client %s", keycloak_client_id)
    try:
        keycloak_admin.add_mapper_to_client(
            keycloak_client_id,
            payload={
                "protocol": "openid-connect",
                "config": {
                    "id.token.claim": "false",
                    "access.token.claim": "false",
                    "userinfo.token.claim": "true",
                    "remote.parameters.username": "true",
                    "remote.parameters.clientid": "true",
                    "client.publickey": "X-VirtruPubKey",
                    "claim.name": "tdf_claims",
                },
                "name": "Virtru OIDC UserInfo Mapper",
                "protocolMapper": "virtru-oidc-protocolmapper",
            },
        )
    except Exception as e:
        logger.warning(
            "Could not add custom userinfo mapper to client %s - this likely means it is already there, so we can ignore this.",
            keycloak_client_id,
        )
        logger.warning(
            "Unfortunately python-keycloak doesn't seem to have a 'remove-mapper' function"
        )
        logger.warning(str(e))
    try:
        keycloak_admin.add_mapper_to_client(
            keycloak_client_id,
            payload={
                "protocol": "openid-connect",
                "config": {
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "false",
                    "remote.parameters.username": "true",
                    "remote.parameters.clientid": "true",
                    "client.publickey": "X-VirtruPubKey",
                    "claim.name": "tdf_claims",
                },
                "name": "Virtru OIDC Auth Mapper",
                "protocolMapper": "virtru-oidc-protocolmapper",
            },
        )
    except Exception as e:
        logger.warning(
            "Could not add custom auth mapper to client %s - this likely means it is already there, so we can ignore this.",
            keycloak_client_id,
        )
        logger.warning(
            "Unfortunately python-keycloak doesn't seem to have a 'remove-mapper' function"
        )
        logger.warning(str(e))


def addVirtruDCRSPIREMapper(keycloak_admin, keycloak_client_id):
    logger.info("Assigning custom SPIRE mapper to client %s", keycloak_client_id)
    try:
        keycloak_admin.add_mapper_to_client(
            keycloak_client_id,
            payload={
                "protocol": "openid-connect",
                "config": {
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "true",
                    "user_workload.namespace": "default",
                    "user_workload.parentid": "spiffe://example.org/ns/spire/sa/spire-agent",
                    "user_workload.selectors": "k8s:pod-label:tdfdatacleanroom:enabled, k8s:ns:default"
                },
                "name": "DCR Spire Registration Mapper",
                "protocolMapper": "virtru-spire-protocolmapper",
            },
        )
    except Exception as e:
        logger.warning(
            "Could not add custom spire mapper to client %s - this likely means it is already there, so we can ignore this.",
            keycloak_client_id,
        )
        logger.warning(
            "Unfortunately python-keycloak doesn't seem to have a 'remove-mapper' function"
        )
        logger.warning(str(e))


def createTestClientForX509Flow(keycloak_admin):
    client_id = "client_x509"
    clients = keycloak_admin.get_clients()
    client_exist = check_matched({"clientId": client_id}, clients)
    if not client_exist:
        logger.debug("Creating client %s configured for x509 flow", client_id)
        keycloak_admin.create_client(
            payload={
                "clientId": client_id,
                "publicClient": "false",
                "standardFlowEnabled": "true",
                "clientAuthenticatorType": "client-x509",
                "baseUrl": "https://local.virtru.com/",
                "protocol": "openid-connect",
                "redirectUris": ["https://local.virtru.com/*"],
                "webOrigins": ["+"],
                "attributes": {"x509.subjectdn": "CN=(.*)(?:$)"},
            },
            skip_exists=True,
        )

        keycloak_client_id = keycloak_admin.get_client_id(client_id)
        logger.info("Created client %s", keycloak_client_id)

        addVirtruMappers(keycloak_admin, keycloak_client_id)


def createTestClientForClientCredentialsFlow(
    keycloak_admin, keycloak_auth_url, client_id
):
    client_secret = os.getenv("CLIENT_SECRET", "123-456")
    logger.debug("Creating client %s configured for clientcreds flow", client_id)
    keycloak_admin.create_client(
        payload={
            "clientId": client_id,
            "directAccessGrantsEnabled": "true",
            "clientAuthenticatorType": "client-secret",
            "secret": client_secret,
            "serviceAccountsEnabled": "true",
            "publicClient": "false",
            "redirectUris": [keycloak_auth_url + "admin/" + client_id + "/console"],
            "attributes": {
                "user.info.response.signature.alg": "RS256"
            },  # Needed to make UserInfo return signed JWT
        },
        skip_exists=True,
    )

    keycloak_client_id = keycloak_admin.get_client_id(client_id)
    logger.info("Created client %s", keycloak_client_id)

    addVirtruMappers(keycloak_admin, keycloak_client_id)


def createTestClientForBrowserAuthFlow(keycloak_admin):
    client_id = "browsertest"
    logger.debug("Creating client %s configured for browser auth flow", client_id)
    keycloak_admin.create_client(
        payload={
            "clientId": client_id,
            "publicClient": "true",
            "standardFlowEnabled": "true",
            "baseUrl": "https://local.virtru.com/",
            "protocol": "openid-connect",
            "redirectUris": ["https://local.virtru.com/*"],
            "webOrigins": ["+"],
            "attributes": {
                "user.info.response.signature.alg": "RS256"
            },  # Needed to make UserInfo return signed JWT
        },
        skip_exists=True,
    )

    keycloak_client_id = keycloak_admin.get_client_id(client_id)
    logger.info("Created client %s", keycloak_client_id)

    addVirtruMappers(keycloak_admin, keycloak_client_id)


def createTestClientTDFClient(keycloak_admin, base_url):
    client_id = "tdf-client"
    logger.debug("Creating client %s configured for browser auth flow", client_id)
    keycloak_admin.create_client(
        payload={
            "clientId": client_id,
            "publicClient": "true",
            "standardFlowEnabled": "true",
            "fullScopeAllowed": "false",
            "baseUrl": base_url + "/",
            "protocol": "openid-connect",
            "redirectUris": [base_url + "/*"],
            "webOrigins": ["+"],
            "attributes": {
                "user.info.response.signature.alg": "RS256"
            },  # Needed to make UserInfo return signed JWT
        },
        skip_exists=True,
    )

    keycloak_client_id = keycloak_admin.get_client_id(client_id)
    logger.info("Created client %s", keycloak_client_id)

    addVirtruMappers(keycloak_admin, keycloak_client_id)


def createTestClientTDFAttributes(keycloak_admin):
    client_id = "tdf-attributes"
    base_url = os.getenv("ATTRIBUTE_AUTHORITY_HOST", "http://localhost:4020")
    logger.debug("Creating client %s configured for browser auth flow", client_id)
    keycloak_admin.create_client(
        payload={
            "clientId": client_id,
            "publicClient": "true",
            "standardFlowEnabled": "true",
            "fullScopeAllowed": "false",
            "baseUrl": base_url + "/",
            "protocol": "openid-connect",
            "redirectUris": [base_url + "/*"],
            "webOrigins": ["+"],
            "attributes": {
                "user.info.response.signature.alg": "RS256"
            },  # Needed to make UserInfo return signed JWT
        },
        skip_exists=True,
    )

    keycloak_client_id = keycloak_admin.get_client_id(client_id)
    logger.info("Created client %s", keycloak_client_id)

    addVirtruMappers(keycloak_admin, keycloak_client_id)


def createTestClientTDFEntitlements(keycloak_admin):
    client_id = "tdf-entitlement"
    base_url = os.getenv("ENTITLEMENT_HOST", "http://localhost:4030")
    logger.debug("Creating client %s configured for browser auth flow", client_id)
    keycloak_admin.create_client(
        payload={
            "clientId": client_id,
            "publicClient": "true",
            "standardFlowEnabled": "true",
            "fullScopeAllowed": "false",
            "baseUrl": base_url + "/",
            "protocol": "openid-connect",
            "redirectUris": [base_url + "/*"],
            "webOrigins": ["+"],
            "attributes": {
                "user.info.response.signature.alg": "RS256"
            },  # Needed to make UserInfo return signed JWT
        },
        skip_exists=True,
    )

    keycloak_client_id = keycloak_admin.get_client_id(client_id)
    logger.info("Created client %s", keycloak_client_id)

    addVirtruMappers(keycloak_admin, keycloak_client_id)


def createTestClientForAbacusWebAuth(keycloak_admin):
    client_id = "abacus-web"
    logger.debug("Creating client %s configured for DCR Jupyter auth flow", client_id)
    keycloak_admin.create_client(
        payload={
            "clientId": client_id,
            "publicClient": "true",
            "standardFlowEnabled": "true",
            "clientAuthenticatorType": "client-secret",
            "serviceAccountsEnabled": "true",
            "protocol": "openid-connect",
            "redirectUris": [
                "http://localhost*",
                "https://demo.secure-analytics-sandbox.virtru.com*",
            ],
            "webOrigins": ["+"],
        },
        skip_exists=True,
    )

    keycloak_client_id = keycloak_admin.get_client_id(client_id)
    logger.info("Created client %s", keycloak_client_id)

    addVirtruClientAudienceMapper(keycloak_admin, keycloak_client_id, "tdf-entitlement")
    addVirtruClientAudienceMapper(keycloak_admin, keycloak_client_id, "tdf-attributes")


def createTestClientForDCRAuth(keycloak_admin):
    client_id = "dcr-test"
    client_secret = "123-456"
    logger.debug("Creating client %s configured for DCR Jupyter auth flow", client_id)
    keycloak_admin.create_client(
        payload={
            "clientId": client_id,
            "secret": client_secret,
            "publicClient": "true",
            "standardFlowEnabled": "true",
            "clientAuthenticatorType": "client-secret",
            "serviceAccountsEnabled": "true",
            "baseUrl": "https://keycloak-http:8080/",
            "protocol": "openid-connect",
            "redirectUris": ["http://localhost*"],
            "webOrigins": ["+"],
        },
        skip_exists=True,
    )

    keycloak_client_id = keycloak_admin.get_client_id(client_id)
    logger.info("Created client %s", keycloak_client_id)

    addVirtruClientAudienceMapper(keycloak_admin, keycloak_client_id, "tdf-entitlement")
    addVirtruClientAudienceMapper(keycloak_admin, keycloak_client_id, "tdf-attributes")

    addVirtruMappers(keycloak_admin, keycloak_client_id)
    addVirtruDCRSPIREMapper(keycloak_admin, keycloak_client_id)


def createTestClientForExchangeFlow(keycloak_admin, keycloak_auth_url):
    client_id = "exchange-target"
    client_secret = "12345678"
    logger.debug("Creating client %s configured for clientcreds flow", client_id)
    keycloak_admin.create_client(
        payload={
            "clientId": client_id,
            "directAccessGrantsEnabled": "true",
            "clientAuthenticatorType": "client-secret",
            "secret": client_secret,
            "serviceAccountsEnabled": "true",
            "publicClient": "false",
            "redirectUris": [keycloak_auth_url + "admin/" + client_id + "/console"],
            "attributes": {
                "user.info.response.signature.alg": "RS256"
            },  # Needed to make UserInfo return signed JWT
        },
        skip_exists=True,
    )

    keycloak_client_id = keycloak_admin.get_client_id(client_id)
    logger.info("Created client %s", keycloak_client_id)

    addVirtruMappers(keycloak_admin, keycloak_client_id)


def assignViewRolesToUser(keycloak_admin, user_id):

    realmManagerClient = keycloak_admin.get_client_id("realm-management")

    viewClients = keycloak_admin.get_client_role(realmManagerClient, "view-clients")
    viewUsers = keycloak_admin.get_client_role(realmManagerClient, "view-users")

    logger.info("Got viewClients role %s", viewClients)

    logger.info("Adding clients/users role to user %s", user_id)
    keycloak_admin.assign_client_role(
        user_id, realmManagerClient, roles=[viewClients, viewUsers]
    )


def createAuthFlowX509(keycloak_admin, realm_name, flow_name, provider_name):
    flows_auth = keycloak_admin.get_authentication_flows()
    flow_exist = check_matched({"alias": flow_name}, flows_auth)
    if not flow_exist:
        if provider_name == "auth-x509-client-username-form":
            keycloak_admin.copy_authentication_flow(
                payload={"newName": flow_name}, flow_alias="browser"
            )
        else:
            keycloak_admin.copy_authentication_flow(
                payload={"newName": flow_name}, flow_alias="direct grant"
            )

    flows_execution = keycloak_admin.get_authentication_flow_executions(flow_name)
    filtered_flow = check_matched({"providerId": provider_name}, flows_execution)
    if filtered_flow:
        payload_config = {
            "alias": flow_name + "_Config",
            "config": {
                "x509-cert-auth.canonical-dn-enabled": "false",
                "x509-cert-auth.mapper-selection.user-attribute-name": "usercertificate",
                "x509-cert-auth.serialnumber-hex-enabled": "false",
                "x509-cert-auth.regular-expression": "(.*?)(?:$)",
                "x509-cert-auth.mapper-selection": "Username or Email",
                "x509-cert-auth.crl-relative-path": "crl.pem",
                "x509-cert-auth.crldp-checking-enabled": "false",
                "x509-cert-auth.mapping-source-selection": "Subject's e-mail",
                "x509-cert-auth.timestamp-validation-enabled": "true",
            },
        }
        flow_id = filtered_flow[0]["id"]
        params_path = {"realm-name": realm_name, "flow-id": flow_id}
        conn = keycloak_admin.connection
        conn.raw_post(
            URL_ADMIN_AUTHENTICATOR_EXECUTION_CONFIG.format(**params_path),
            data=json.dumps(payload_config),
        )

    if provider_name == "auth-x509-client-username-form":
        keycloak_admin.update_realm(realm_name, payload={"browserFlow": flow_name})
    else:
        # Make password auth for direct grants optional.
        # Otherwise, it'll require a password even if you have a client certificate.
        filtered_flow = check_matched(
            {"providerId": "direct-grant-validate-password"}, flows_execution
        )
        if filtered_flow:
            flow_id = filtered_flow[0]["id"]
            payload_config = {"id": flow_id, "requirement": "ALTERNATIVE"}
            params_path = {"realm-name": realm_name, "flow-alias": flow_name}
            conn = keycloak_admin.connection
            # We need to do this manually because KeycloakAdmin expects a 204 response and sometimes we get a valid 202.  :/
            conn.raw_put(
                URL_ADMIN_EXECUTION_FLOW.format(**params_path),
                data=json.dumps(payload_config),
            )
            keycloak_admin.update_realm(
                realm_name, payload={"directGrantFlow": flow_name}
            )


def updateMasterRealm(kc_admin_user, kc_admin_pass, kc_url):
    logger.debug("Login admin %s %s", kc_url, kc_admin_user)
    keycloak_admin = KeycloakAdmin(
        server_url=kc_url,
        username=kc_admin_user,
        password=kc_admin_pass,
        realm_name="master",
    )

    # Create test client in `master` configured for Abacus cross-realm user/client queries
    createTestClientForAbacusWebAuth(keycloak_admin)


def createTDFRealm(kc_admin_user, kc_admin_pass, kc_url):
    realm_name = "tdf"

    logger.debug("Login admin %s %s", kc_url, kc_admin_user)
    keycloak_admin = KeycloakAdmin(
        server_url=kc_url,
        username=kc_admin_user,
        password=kc_admin_pass,
        realm_name="master",
    )

    realms = keycloak_admin.get_realms()
    realm_exist = check_matched({"realm": realm_name}, realms)
    if not realm_exist:
        logger.info("Create realm %s", realm_name)
        keycloak_admin.create_realm(
            # payload={"realm": realm_name, "enabled": "true", "attributes": {"frontendUrl": "http://keycloak-http:8080/auth/realms/tdf"}}, skip_exists=True
            payload={"realm": realm_name, "enabled": "true"},
            skip_exists=True,
        )

    keycloak_admin = KeycloakAdmin(
        server_url=kc_url,
        username=kc_admin_user,
        password=kc_admin_pass,
        realm_name=realm_name,
        user_realm_name="master",
    )

    # Create test client configured for clientcreds auth flow
    createTestClientForClientCredentialsFlow(keycloak_admin, kc_url, "tdf-client")
    npeClientStr = os.getenv("npeClients")
    if npeClientStr is not None:
        for npe_client_id in npeClientStr.split(","):
            createTestClientForClientCredentialsFlow(
                keycloak_admin, kc_url, npe_client_id
            )

    # Create test client configured for browser auth flow
    createTestClientForBrowserAuthFlow(keycloak_admin)

    # Create test client configured for exchange auth flow
    createTestClientForExchangeFlow(keycloak_admin, kc_url)

    # Create test client configured for exchange auth flow
    createTestClientForDCRAuth(keycloak_admin)

    # Create attributes test client
    createTestClientTDFAttributes(keycloak_admin)

    # Create entitlements test client
    createTestClientTDFEntitlements(keycloak_admin)

    createUsersInRealm(keycloak_admin)


def createTDFPKIRealm(kc_admin_user, kc_admin_pass, kc_url):
    # BEGIN PKI
    realm_name = "tdf-pki"

    logger.debug("Login admin %s %s", kc_url, kc_admin_user)
    keycloak_admin = KeycloakAdmin(
        server_url=kc_url,
        username=kc_admin_user,
        password=kc_admin_pass,
        realm_name="master",
    )

    realms = keycloak_admin.get_realms()
    realm_exist = check_matched({"realm": realm_name}, realms)
    if not realm_exist:
        logger.info("Create realm %s", realm_name)
        keycloak_admin.create_realm(
            payload={
                "realm": realm_name,
                "enabled": "true",
                "attributes": {
                    "frontendUrl": "http://keycloak-http/auth/realms/tdf-pki"
                },
            },
            skip_exists=True,
        )

    keycloak_admin = KeycloakAdmin(
        server_url=kc_url,
        username=kc_admin_user,
        password=kc_admin_pass,
        realm_name=realm_name,
        user_realm_name="master",
    )

    # Create test client configured for clientcreds auth flow
    createTestClientForClientCredentialsFlow(keycloak_admin, kc_url, "tdf-client")

    # Create test client configured for browser auth flow
    createTestClientForBrowserAuthFlow(keycloak_admin)

    # X.509 Client Certificate Authentication to a Browser Flow
    # https://www.keycloak.org/docs/latest/server_admin/index.html#adding-x-509-client-certificate-authentication-to-a-browser-flow
    createAuthFlowX509(
        keycloak_admin, realm_name, "X509_Browser", "auth-x509-client-username-form"
    )

    # X.509 Client Certificate Authentication to a Direct Grant Flow
    # https://www.keycloak.org/docs/latest/server_admin/index.html#adding-x-509-client-certificate-authentication-to-a-direct-grant-flow
    createAuthFlowX509(
        keycloak_admin,
        realm_name,
        "X509_Direct_Grant",
        "direct-grant-auth-x509-username",
    )

    createTestClientForX509Flow(keycloak_admin)

    createUsersInRealm(keycloak_admin)

    # END PKI


def kc_bootstrap():
    username = os.getenv("keycloak_admin_username")
    password = os.getenv("keycloak_admin_password")

    keycloak_hostname = os.getenv("keycloak_hostname", "http://localhost:8080")
    keycloak_auth_url = keycloak_hostname + "/auth/"

    updateMasterRealm(username, password, keycloak_auth_url)
    createTDFRealm(username, password, keycloak_auth_url)
    createTDFPKIRealm(username, password, keycloak_auth_url)

    return True  # It is pointless to return True here, as we arent' checking the return values of the previous calls (and don't really need to)
