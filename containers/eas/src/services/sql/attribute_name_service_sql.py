"""SQL Attribute Service."""

import logging
from sqlite3 import IntegrityError
from typing import Any, Dict, List, Optional

from ...db_connectors import SQLiteConnector
from ...eas_config import EASConfig
from ...errors import (
    AttributeExistsError,
    ConfigurationError,
    MalformedAttributeError,
    NotFound,
)
from ...models import AttributeName, AttributeValue, RuleType, State
from ...services import (
    AbstractAttributeNameService,
    AbstractAttributeService,
    AbstractAuthorityNamespaceService,
)

SERVICE_NAME = "Attribute Name Service"
eas_config = EASConfig.get_instance()

logger = logging.getLogger(__name__)


class AttributeNameServiceSQL(AbstractAttributeNameService):
    def __init__(
        self,
        authority_ns_service: AbstractAuthorityNamespaceService,
        attribute_service: AbstractAttributeService,
        default_namespace: str,
    ):
        self.default_namespace: str
        if default_namespace is None:
            self.default_namespace = eas_config.get_item("DEFAULT_NAMESPACE")
        else:
            self.default_namespace = default_namespace
        if not authority_ns_service:
            raise ConfigurationError("Attribute Name Service is required")
        self.authority_ns_service: AbstractAuthorityNamespaceService = (
            authority_ns_service
        )
        self.attribute_service: AbstractAttributeService = attribute_service
        self.connector: SQLiteConnector = SQLiteConnector.get_instance()

    def create(self, attribute_name_raw: dict) -> dict:
        """Create a new Attribute Name.

        Return the request body if the operation was successful, otherwise
        raise an error.
        """
        logger.debug("%s: CREATE %s", SERVICE_NAME, attribute_name_raw)
        attr_name = AttributeName.from_raw_dict(attribute_name_raw)

        # Get namespace, check if exists, then create if missing.
        if not self.authority_ns_service.get(attr_name.authorityNamespace):
            self.authority_ns_service.create(
                {"namespace": attr_name.authorityNamespace, "isDefault": False}
            )

        try:
            # Insert the attribute name record
            command = """
                    INSERT INTO attributeName
                        (namespace, name, "order", state, rule)
                    VALUES
                        (?, ?, ?, ?, ?)
                    """
            parameters = (
                attr_name.authorityNamespace,
                attr_name.name,
                "|".join(attr_name.order),
                attr_name.state.value,
                attr_name.rule.to_string(),
            )
            result = self.connector.run(command, parameters)
            assert result
        except IntegrityError:
            raise AttributeExistsError("This attribute name already exists.")

        # If order is provided, ensure the values listed are added to database
        if attr_name.order:
            for value in attr_name.order:
                attribute_uri = AttributeValue.make_uri(
                    attr_name.authorityNamespace, attr_name.name, value
                )
                logger.debug("Checking that 'order' values exist: %s", attribute_uri)
                try:
                    self.attribute_service.create(
                        {
                            "authorityNamespace": attr_name.authorityNamespace,
                            "name": attr_name.name,
                            "value": value,
                            "attribute": attribute_uri,
                        }
                    )
                    logger.debug("  %s attribute created.", attribute_uri)
                except AttributeExistsError:
                    logger.debug("  %s attribute already exists.", attribute_uri)

        return attr_name.to_raw_dict()

    def get(self, namespace: str, name: str) -> dict:
        """Retrieve a single Attribute Name as a dict."""
        logger.debug("%s: GET %s,%s", SERVICE_NAME, namespace, name)
        if not namespace:
            namespace = eas_config.get_item("DEFAULT_NAMESPACE")
        command = """
                    SELECT namespace, name, "order", state, rule
                    FROM attributeName
                    WHERE
                        namespace=? AND
                        name=?
                """
        parameters = (namespace, name)
        result = self.connector.run(command, parameters).fetchall()
        if not result:
            raise NotFound(
                message=f"Attribute Name {name} not found in namespace {namespace}."
            )
        return {
            "authorityNamespace": result[0][0],
            "name": result[0][1],
            "order": (result[0][2]).split("|"),
            "state": State.from_input(result[0][3]).name.lower(),
            "rule": RuleType.from_input(result[0][4]).to_string(),
        }

    def find(self, namespace: str = None) -> List[Optional[dict]]:
        """Retrieve all Attribute Names - returns list of dict objects.

        If provided, filter by authority namespace"""

        logger.debug("%s: FIND %s", SERVICE_NAME, namespace)
        parameters: tuple
        if namespace:
            command = """
                        SELECT namespace, name, "order", state, rule
                        FROM attributeName
                        WHERE
                            namespace=? 
                    """
            parameters = (namespace,)
        else:
            command = """
                        SELECT namespace, name, "order", state, rule
                        FROM attributeName
                    """
            parameters = ()
        results = self.connector.run(command, parameters).fetchall()

        results_list: List[Optional[Dict[Any, Any]]] = []
        for result in results:
            # Get the URI using AttributeName model
            _rule: RuleType = RuleType.from_input(result[4])
            _raw_item = {
                "authorityNamespace": result[0],
                "name": result[1],
                "order": (result[2]).split("|"),
                "state": State.from_input(result[3]).to_string(),
                "rule": _rule.to_string(),
            }
            a = AttributeName.from_raw_dict(_raw_item)
            results_list.append(a.to_raw_dict())
        return results_list

    def get_many(self, uris: List[str]) -> List[dict]:
        """Retrieve a list of attribute names - designed for KAS attribute discovery."""
        logger.debug("%s: GET_MANY %s", SERVICE_NAME, uris)

        # TODO: Use 1 SQL call
        all_results = []
        for uri in uris:
            a = AttributeName.from_uri(uri)
            raw_item = self.get(a.authorityNamespace, a.name)
            all_results.append(raw_item)

        return all_results

    def update(self, body: dict, attribute_name: str, namespace: str = "") -> dict:
        """Update fields of attribute name and return updated attribute name."""
        # use default namespace if none provided
        if not namespace:
            namespace = eas_config.get_item("DEFAULT_NAMESPACE")
        namespace = namespace.lower()  # case insensitivity for namespaces

        # Check if attribute name is in table
        if not self.get(namespace, attribute_name):
            raise NotFound(
                f"Cannot update attribute name {attribute_name} because attribute name does not exist."
            )

        # Try to form an attributeName model with the provided info
        # from_raw_dict will raise MalformedAttributeError if invalid body
        name = AttributeName.from_raw_dict(body)

        # Update the attribute record
        self.connector.run(
            """
            UPDATE attributeName
            SET "order"= ?, state= ?, rule= ?
            WHERE name= ? AND namespace= ?
            """,
            (
                "|".join(name.order),
                name.state.value,
                name.rule.to_string(),
                attribute_name,
                namespace,
            ),
        )

        return name.to_raw_dict()

    def patch(self, body: dict, attribute_name: str, namespace: str = None) -> dict:
        """Only update fields of attribute name provided in body and return updated attribute name."""
        logger.debug("here 0")
        if not isinstance(body, dict):
            raise MalformedAttributeError(
                "For PATCH, each item in the list must be a dict"
            )
        if not namespace:
            raise MalformedAttributeError("namespace is required")

        # Check if attribute name is in table
        current_attr = self.get(namespace, attribute_name)
        if not current_attr:
            raise NotFound(
                f"Cannot patch attribute (name={attribute_name}, namespace={namespace}) because attribute name does not exist."
            )

        # make patches
        for key in body.keys():
            if key not in ["authorityNamespace", "attribute_name"]:
                current_attr[key] = body[key]

        # construct model with patches
        patch_attr_name = AttributeName.from_raw_dict(current_attr)
        if not patch_attr_name:
            raise MalformedAttributeError(
                f"Cannot create an attribute from {current_attr}"
            )

        # Update the attribute record
        self.connector.run(
            """
            UPDATE attributeName
            SET "order"= ?, state= ?, rule= ?
            WHERE name= ? AND namespace= ?
            """,
            (
                "|".join(patch_attr_name.order),
                patch_attr_name.state.value,
                patch_attr_name.rule.to_string(),
                attribute_name,
                namespace,
            ),
        )

        return patch_attr_name.to_raw_dict()
