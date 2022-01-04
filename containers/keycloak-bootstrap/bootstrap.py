#!/usr/bin/env python3

import logging
from keycloak_bootstrap import kc_bootstrap
from entitlements_bootstrap import entitlements_bootstrap

logging.basicConfig()
logger = logging.getLogger("keycloak_bootstrap")
logger.setLevel(logging.DEBUG)


def main():
    logger.info("Running Keycloak bootstrap")
    kc_bootstrap()
    logger.info("Running Entitlement/PGSQL bootstrap")
    entitlements_bootstrap()


if __name__ == "__main__":
    main()
