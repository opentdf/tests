#!/usr/bin/env python3

import os
import logging
from keycloak import KeycloakAdmin

logging.basicConfig()
logger = logging.getLogger("keycloak_bootstrap")
logger.setLevel(logging.DEBUG)

keycloak_hostname = os.getenv("keycloak_hostname", "http://localhost:8080")
keycloak_auth_url = keycloak_hostname + "/auth/"


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
                    "remote.url": "http://attribute-provider:5000",
                },
                "name": "Virtru OIDC UserInfo Mapper",
                "protocolMapper": "virtru-oidc-protocolmapper",
            },
        )
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
                    "remote.url": "http://attribute-provider:5000",
                },
                "name": "Virtru OIDC Auth Mapper",
                "protocolMapper": "virtru-oidc-protocolmapper",
            },
        )
    except Exception as e:
        logger.warning(str(e))


def createTestClientForClientCredentialsFlow(keycloak_admin):
    client_id = os.getenv("CLIENT_ID", "tdf-client")
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

    for username in ("user1", "user2"):
        new_user = keycloak_admin.create_user(
            {
                "username": username,
                "enabled": True,
                "credentials": [
                    {
                        "value": "password",
                        "type": "password",
                    }
                ],
            }
        )
    logger.info("Created new user %s", new_user)
    return True


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

    for username in ("testuser@virtru.com"):
        new_user = keycloak_admin.create_user(
            {
                "username": username,
                "enabled": True,
                "credentials": [
                    {
                        "value": "testuser123",
                        "type": "password",
                    }
                ],
            }
        )

    logger.info("Created new user %s", new_user)
    return True


def main():
    global logger
    keycloak_admin_username = os.getenv("keycloak_admin_username")
    keycloak_admin_password = os.getenv("keycloak_admin_password")
    realm_name = os.getenv("realm", "tdf")

    logger.debug("Login admin %s %s", keycloak_auth_url, keycloak_admin_username)
    keycloak_admin = KeycloakAdmin(
        server_url=keycloak_auth_url,
        username=keycloak_admin_username,
        password=keycloak_admin_password,
        realm_name="master",
    )

    logger.info("Create realm %s", realm_name)
    keycloak_admin.create_realm(
        payload={"realm": realm_name, "enabled": "true"}, skip_exists=True
    )

    keycloak_admin = KeycloakAdmin(
        server_url=keycloak_auth_url,
        username=keycloak_admin_username,
        password=keycloak_admin_password,
        realm_name=realm_name,
        user_realm_name="master",
    )

    # Create test client configured for clientcreds auth flow
    res = createTestClientForClientCredentialsFlow(keycloak_admin)
    if res != True:
        raise Exception("Could not create clientcreds client")

    # Create test client configured for browser auth flow
    res = createTestClientForBrowserAuthFlow(keycloak_admin)
    if res != True:
        raise Exception("Could not create browser client")

    return True


if __name__ == "__main__":
    main()
