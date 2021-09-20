"""Authority Namespace Service SQLite."""

import logging
from typing import List, Optional

from ..abstract_authority_ns_service import AbstractAuthorityNamespaceService
from ...db_connectors import SQLiteConnector
from ...errors import AuthorityNamespaceExistsError, MalformedAuthorityNamespaceError
from ...models.authority_namespace import AuthorityNamespace

logger = logging.getLogger(__name__)


class AuthorityNamespaceSql(AbstractAuthorityNamespaceService):
    """Authority Namespace Services data connector."""

    def __init__(self) -> None:
        """Construct data connector with db path."""
        self.connector = SQLiteConnector.get_instance()

    def create(self, body: dict) -> dict:
        """Create a new authority namespace."""
        logger.debug("Creating new authority namespace with body = %s", body)
        if "namespace" not in body or "isDefault" not in body:
            raise MalformedAuthorityNamespaceError(
                "namespace and isDefault properties are required for an authority namespace."
            )
        namespace = body["namespace"].lower()  # case insensitivity for namespaces
        isDefault = body["isDefault"]
        displayName = ""
        if "displayName" in body:
            displayName = body["displayName"]

        # Check to see if namespace exists
        if self.retrieve(namespace=namespace):
            raise AuthorityNamespaceExistsError(f"Duplicate namespace {namespace} ")

        # Insert the basic namespace record
        command = """
                INSERT INTO authorityNamespace
                    ("namespace", "isDefault", "displayName")
                VALUES
                    (?, ?, ?)
            """
        parameters = (namespace, isDefault, displayName)
        namespace_result = self.connector.run(command, parameters)
        assert namespace_result

        return {
            "namespace": namespace,
            "isDefault": isDefault,
            "displayName": displayName,
        }

    def retrieve(self, isDefault: bool = False, namespace: str = None) -> List[str]:
        """Retrieve one or more namespaces as a list of strings"""
        # retrieve given namespace
        parameters: tuple
        if isDefault and namespace:
            raise NotImplementedError(
                "Retrieve does not support isDefault and namespace parameters in the same request"
            )

        if namespace:
            namespace = namespace.lower()  # case insensitivity for namespaces
            logger.debug("authority_ns_service_sql.retrieve(namespace=%s)", namespace)
            command = """SELECT namespace, isDefault, displayName FROM authorityNamespace WHERE namespace = ?"""
            parameters = (namespace,)

        elif isDefault:
            logger.debug("authority_ns_service_sql.retrieve(isDefault=%s)", isDefault)
            command = """SELECT namespace, isDefault, displayName FROM authorityNamespace WHERE isDefault = ?"""
            parameters = (isDefault,)

        else:
            logger.debug("authority_ns_service_sql.retrieve(all)")
            command = (
                """SELECT namespace, isDefault, displayName FROM authorityNamespace"""
            )
            parameters = ()

        results = self.connector.run(command, parameters).fetchall()
        logger.debug("Results = %s", results)

        result_set = []
        for (result_namespace, result_default, result_display_name) in results:
            result_set.append(result_namespace)

        return result_set

    def get(self, namespace: str) -> Optional[AuthorityNamespace]:
        namespace = namespace.lower()  # case insensitivity for namespaces
        logger.debug("authority_ns_service_sql.retrieve(%s)", namespace)
        command = """SELECT namespace, isDefault, displayName FROM authorityNamespace WHERE namespace = ?"""
        parameters = (namespace,)

        results = self.connector.run(command, parameters).fetchall()
        if not results:
            return None
        (result_namespace, result_default, result_display_name) = results[0]
        return AuthorityNamespace(result_namespace, result_default, result_namespace)
