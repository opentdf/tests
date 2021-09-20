"""SQL Attribute Service."""

import logging
from typing import Dict, List

from ..abstract_attribute_service import AbstractAttributeService
from ...db_connectors import SQLiteConnector
from ...errors import (
    AttributeExistsError,
    ConfigurationError,
    MalformedAttributeError,
    NotFound,
)
from ...models import AttributeValue, State

logger = logging.getLogger(__name__)


class AttributeServiceSql(AbstractAttributeService):
    """Attribute Service SQL."""

    def __init__(
        self,
        *,
        eas_private_key: str,
        default_kas_url: str,
        default_kas_certificate: str,
    ):
        """Initialize Attribute Service."""

        if eas_private_key is None or eas_private_key == "":
            raise ConfigurationError("missing eas private key")
        if default_kas_url is None or default_kas_url == "":
            raise ConfigurationError("missing default kas url")
        if default_kas_certificate is None or default_kas_certificate == "":
            raise ConfigurationError("missing default public key")

        self.__eas_private_key: str = eas_private_key
        self.__default_kas_certificate: str = default_kas_certificate
        self.__default_kas_url: str = default_kas_url
        self.connector = SQLiteConnector.get_instance()

    def create(self, body: dict) -> AttributeValue:
        """Create an attribute record in the store.

        Only the "attribute" url field is required in the body object. The
        other values will be set to defaults.

        Indicate failure by returning None.  Successful calls to this method
        should return the newly created attribute's object.
        """
        logger.debug("Attribute body = %s", body)

        if "default_pub_key" not in body:
            pub_key = self.__default_kas_certificate
            logger.debug("Using default public key")
            body["pubKey"] = pub_key

        if "kasUrl" not in body:
            kas_url = self.__default_kas_url
            logger.debug("Using default kas URL = %s", kas_url)
            body["kasUrl"] = kas_url

        attr_value = AttributeValue.from_raw_dict(body)
        # Check for uniqueness
        if self.retrieve([attr_value.attribute]):
            raise AttributeExistsError(
                f"Attribute {attr_value.attribute} already exists."
            )
        self.create_name_if_required(attr_value)

        command = """
                INSERT INTO attributeValue
                    ("namespace", "name", "value", "displayName", "kasUrl", "isDefault", "state", "pubKey")
                VALUES
                    (?,?,?,?,?,?,?,?)
            """
        parameters = (
            attr_value.authorityNamespace,
            attr_value.name,
            attr_value.value,
            attr_value.display_name,
            body.get("kasUrl"),
            attr_value.is_default,
            attr_value.state,
            body.get("pubKey"),
        )
        results = self.connector.run(command, parameters)

        logger.debug("Attribute Created. Last row ID = %s", results.lastrowid)
        # Fetch the newly created attribute from the database to return
        retrieve = self.retrieve([attr_value.attribute])
        assert len(retrieve) == 1
        return retrieve[0]

    def read(self) -> List[dict]:
        """Read all attribute records."""
        command = """
            SELECT url, displayName, kasUrl, pubKey, state FROM attribute
        """
        parameters = None

        results = self.connector.run(command, parameters).fetchall()
        logger.debug("Read results = %s", results)

        result_set = []
        for result in results:
            result_set.append(
                {
                    "attribute": result[0],
                    "displayName": result[1],
                    "kasUrl": result[2],
                    "pubKey": result[3],
                    "state": State[result[4]].to_string(),
                }
            )
        return result_set

    def retrieve(
        self, attribute_urls: List[str] = None, kas_certificate: str = None
    ) -> List[AttributeValue]:
        """Read one or more attribute record, selected by attribute uri.

        This method implements retrieve() from abstract_attribute_service.
        """
        logger.debug("retrieve = %s", attribute_urls)
        parameters: tuple
        if not attribute_urls:
            # Return all attributes
            command = """
                SELECT "url", "displayName", "kasUrl", "pubKey", "state" FROM attribute
            """
            parameters = ()
        else:
            if type(attribute_urls) is not list:
                raise MalformedAttributeError(
                    "attribute service retrieve requires a list of attribute urls or None"
                )

            # format command generates a set of question marks for the SQL "IN" operation
            # matching number of attributes urls
            command = """
                SELECT "url", "displayName", "kasUrl", "pubKey", "state" FROM "attribute"
                WHERE "url" in ({})
            """.format(
                ",".join("?" * len(attribute_urls))
            )

            parameters = tuple(attribute_urls)

        results = self.connector.run(command, parameters).fetchall()
        logger.debug("Results = %s", results)
        result_set = []
        for result in results:
            pubkey = result[3]
            assert type(pubkey) == str
            if kas_certificate:
                pubkey = kas_certificate

            attribute_value = AttributeValue.from_raw_dict(
                {
                    "attribute": result[0],
                    "displayName": result[1],
                    "kasUrl": result[2],
                    "pubKey": pubkey,
                    "state": State(result[4]).to_string(),
                }
            )
            result_set.append(attribute_value)
        return result_set

    def retrieve_jwt(
        self, attribute_urls: List[str] = None, kas_certificate: str = None
    ) -> List[Dict[str, str]]:
        """Like retrieve, but return encoded as jwts"""
        attributes: List[AttributeValue] = self.retrieve(
            attribute_urls=attribute_urls, kas_certificate=kas_certificate
        )

        # Use Python List Comprehension to convert list of AttributeValues to jwts
        jwt_list = [
            {"jwt": attribute_value.to_jwt(self.__eas_private_key, algorithm="RS256")}
            for attribute_value in attributes
        ]
        return jwt_list

    def update(self, attr_value: AttributeValue) -> AttributeValue:
        """Update an attribute record. Won't update url because that is identity column.

        :param attr_value: An attribute_value object with the new values.
        :return attribute_value object for the attribute updated."""
        if not isinstance(attr_value, AttributeValue):
            raise MalformedAttributeError(
                f"{type(attr_value)} {attr_value} is not an AttributeValue object"
            )
        command = """
                UPDATE attributeValue
                    SET "displayName" = ?,
                        "kasUrl" = ?,
                        "pubKey" = ?,
                        "state" = ? 
                    WHERE "name" = ?
                      AND "namespace" = ?
                      AND "value" = ?
                """
        # convert to int if enum
        attr_value_state: int = (
            attr_value.state.value
            if isinstance(attr_value.state, State)
            else attr_value.state
        )
        parameters = (
            attr_value.display_name,
            attr_value.kas_url,
            attr_value.pub_key,
            attr_value_state,
            attr_value.name,
            attr_value.authorityNamespace,
            attr_value.value,
        )
        results = self.connector.run(command, parameters)
        result = results.lastrowid
        logger.debug("Update results = %s", result)
        return self.retrieve([attr_value.attribute])[0]

    def delete(self, attribute_url: str) -> AttributeValue:
        """Set one attribute value to inactive."""
        attributes = self.retrieve([attribute_url])
        if not attributes:
            raise NotFound()
        attr_value: AttributeValue = attributes[0]
        attr_value.state = State.INACTIVE

        command = """
                UPDATE "attributeValue"
                SET "state" = ?
                    WHERE "name" = ?
                      AND "namespace" = ?
                      AND "value" = ?
            """
        parameters = (
            attr_value.state.value,
            attr_value.name,
            attr_value.authorityNamespace,
            attr_value.value,
        )
        result = self.connector.run(command, parameters, force_commit=True)
        if result.rowcount:
            return attr_value
        else:
            raise NotFound()

    def get_kas_public_key(self) -> str:
        return self.__default_kas_certificate

    def authority_namespace_exists(self, namespace: str) -> bool:
        command = """
                SELECT namespace
                FROM authorityNamespace
                WHERE
                    namespace=?
            """
        parameters = (namespace,)
        result = self.connector.run(command, parameters).fetchall()
        return bool(len(result))

    def create_namespace_if_required(self, namespace: str) -> None:
        if self.authority_namespace_exists(namespace):
            return
        command = """
                INSERT INTO authorityNamespace
                    ("namespace", "isDefault", "displayName")
                VALUES
                    (?, ?, ?)
            """
        parameters = (namespace, False, None)
        self.connector.run(command, parameters)

    def attr_name_exists(self, namespace: str, name: str) -> bool:
        command = """
                SELECT state
                FROM attributeName
                WHERE
                    namespace=? AND
                    name=?
            """
        parameters = (namespace, name)
        result = self.connector.run(command, parameters).fetchall()
        return bool(len(result))

    def create_name_if_required(self, attribute_value: AttributeValue) -> None:
        """Check whether the Attr Name record already exists, and create if it doesn't/

        To keep the integrity of a database, the attribute name record must exist before the attribute value.

        :param attribute_value attribute_value: The Attribute Value object we wish to create
        :return: True for success, or raise error for failure.
        """

        namespace = attribute_value.authorityNamespace
        name = attribute_value.name

        # Make sure the authority namespace exists.
        self.create_namespace_if_required(namespace)

        if self.attr_name_exists(namespace, name):
            return
        else:
            # Name must be created. Create object from defaults:
            attr_name = attribute_value.get_attribute_name()
            # Insert attribute name into db
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
            update = self.connector.run(command, parameters)
            assert update

    def get_values_for_name(self, namespace: str, name: str) -> List[dict]:
        """Read all attribute values for this attribute name."""
        command = """
            SELECT url, displayName, kasUrl, pubKey, state FROM attribute
            WHERE namespace = ? AND name = ?
        """
        parameters = (namespace, name)

        results = self.connector.run(command, parameters).fetchall()
        logger.debug("Read results = %s", results)

        result_set = []
        for result in results:
            result_set.append(
                {
                    "attribute": result[0],
                    "displayName": result[1],
                    "kasUrl": result[2],
                    "pubKey": result[3],
                    "state": State(result[4]).to_string(),
                }
            )
        return result_set
