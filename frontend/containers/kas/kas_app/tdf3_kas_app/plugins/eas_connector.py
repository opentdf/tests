"""The EAS Connector class."""

import logging
import requests
import json
import os

from tdf3_kas_core.errors import (
    Error,
    InvalidAttributeError,
    RequestTimeoutError,
)

logger = logging.getLogger(__name__)


class EASConnector(object):
    """EAS Connector makes calls to the EAS."""

    def __init__(self, host):
        """Construct a non-functional connector."""

        self._host = host
        self._headers = {
            "Content-Type": "application/json",
        }
        self._requests_timeout = 10  # ten seconds

    def fetch_attributes(self, namespaces):
        """Fetch attributes from EAS."""
        logger.debug("--- Fetch attributes from EAS  [attribute = %s] ---", namespaces)

        uri = "{0}/v1/attrName".format(self._host)
        ca_cert_path = os.environ.get("CA_CERT_PATH")
        client_cert_path = os.environ.get("CLIENT_CERT_PATH")
        client_key_path = os.environ.get("CLIENT_KEY_PATH")

        try:
            if client_cert_path and client_key_path:
                logger.debug("Using cert auth for url:%s", uri)
                resp = requests.post(
                    uri,
                    headers=self._headers,
                    data=json.dumps(namespaces),
                    timeout=self._requests_timeout,
                    cert=(client_cert_path, client_key_path),
                    verify=ca_cert_path,
                )
            else:
                resp = requests.post(
                    uri,
                    headers=self._headers,
                    data=json.dumps(namespaces),
                    timeout=self._requests_timeout,
                    verify=ca_cert_path,
                )
        except (
            requests.exceptions.ConnectTimeout,
            requests.exceptions.ReadTimeout,
        ) as err:
            logger.exception(err)
            logger.setLevel(logging.DEBUG)
            raise RequestTimeoutError(
                "Fetch attributes request connect timed out"
            ) from err
        except requests.exceptions.RequestException as err:
            logger.exception(err)
            logger.setLevel(logging.DEBUG)
            raise InvalidAttributeError("Unable to be fetch attributes") from err

        if resp.status_code != 200:
            logger.debug(
                "--- Fetch attribute %s failed with status %s; reason [%s] ---",
                uri,
                resp.status_code,
                resp.reason,
            )
            return None
        logger.debug("--- Fetch attributes successful --- ")
        res = resp.json()
        logger.debug("Fetch attribute %s => %s", uri, res)
        return res

    def ping(self):
        """Ping EAS."""
        logger.debug("--- Ping EAS] ---")

        uri = "{0}/healthz".format(self._host)
        ca_cert_path = os.environ.get("CA_CERT_PATH")
        client_cert_path = os.environ.get("CLIENT_CERT_PATH")
        client_key_path = os.environ.get("CLIENT_KEY_PATH")

        if client_cert_path and client_key_path:
            logger.debug("Using cert auth for url:%s", uri)
            resp = requests.get(
                uri,
                headers=self._headers,
                timeout=self._requests_timeout,
                cert=(client_cert_path, client_key_path),
                verify=ca_cert_path,
            )
        else:
            resp = requests.get(
                uri,
                headers=self._headers,
                timeout=self._requests_timeout,
                verify=ca_cert_path,
            )

        if 200 <= resp.status_code < 300:
            logger.debug("--- Ping EAS successful --- ")
        else:
            logger.debug(
                "--- Ping EAS %s failed with status %s; reason [%s] ---",
                uri,
                resp.status_code,
                resp.reason,
            )
            raise Error("Unable to be ping EAS")
