"""Ensure the Keycloak realm has the `opentdf-dpop` client test_dpop.py uses.

`service provision keycloak` creates it from service v0.18.0 on. Older
platforms don't, so their lanes would skip every DPoP test. This copies the
`opentdf` client (mappers and service-account realm roles included) under the
new id with DPoP-bound tokens required. Idempotent: an existing client is left
alone.

    uv run python provision_dpop_client.py

Reads KCHOST and REALM (see test.env) and KC_ADMIN_USER / KC_ADMIN_PASSWORD
(default admin / changeme, as the platform's docker-compose sets them).
"""

import os
import sys

import requests

SOURCE_CLIENT = "opentdf"
DPOP_CLIENT = "opentdf-dpop"


def _strip_ids(rep: dict) -> dict:
    return {k: v for k, v in rep.items() if k != "id"}


def main() -> int:
    base = f"{os.getenv('KCHOST', 'http://localhost:8888').rstrip('/')}/auth"
    realm = os.getenv("REALM", "opentdf")
    admin = requests.post(
        f"{base}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": os.getenv("KC_ADMIN_USER", "admin"),
            "password": os.getenv("KC_ADMIN_PASSWORD", "changeme"),
        },
        timeout=30,
    )
    admin.raise_for_status()
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {admin.json()['access_token']}"
    clients = f"{base}/admin/realms/{realm}/clients"

    def client(client_id: str) -> dict | None:
        r = s.get(clients, params={"clientId": client_id}, timeout=30)
        r.raise_for_status()
        return next(iter(r.json()), None)

    if client(DPOP_CLIENT):
        print(f"{DPOP_CLIENT} already exists in realm {realm}")
        return 0
    source = client(SOURCE_CLIENT)
    if not source:
        print(f"realm {realm} has no {SOURCE_CLIENT} client to copy", file=sys.stderr)
        return 1

    rep = _strip_ids(source)
    rep.update(
        clientId=DPOP_CLIENT,
        name=DPOP_CLIENT,
        secret=os.getenv("CLIENTSECRET", "secret"),
        attributes={**source.get("attributes", {}), "dpop.bound.access.tokens": "true"},
        protocolMappers=[_strip_ids(m) for m in source.get("protocolMappers", [])],
    )
    s.post(clients, json=rep, timeout=30).raise_for_status()
    created = client(DPOP_CLIENT)
    assert created

    def sa_roles(c: dict) -> str:
        r = s.get(f"{clients}/{c['id']}/service-account-user", timeout=30)
        r.raise_for_status()
        return f"{base}/admin/realms/{realm}/users/{r.json()['id']}/role-mappings/realm"

    roles = s.get(sa_roles(source), timeout=30)
    roles.raise_for_status()
    s.post(sa_roles(created), json=roles.json(), timeout=30).raise_for_status()
    names = ", ".join(r["name"] for r in roles.json())
    print(f"created {DPOP_CLIENT} in realm {realm} with realm roles [{names}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
