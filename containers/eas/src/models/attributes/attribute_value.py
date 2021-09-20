"""AttributeValue."""

import logging

import jwt

from .attribute_name import AttributeName
from ..state import State
from ...eas_config import EASConfig
from ...errors import MalformedAttributeError
from ...util.keys.get_keys_from_disk import get_key_using_config
from ...validation import attr_desc_check
from ...util.jwt.jwt_utilities import exp_env_to_time

VALUE_ = "/value/"
ATTR_ = "/attr/"

logger = logging.getLogger(__name__)

eas_config = EASConfig.get_instance()


class AttributeValue(object):
    """The AttributeValue Class.

    AttributeValues are quasi-immutable representations of attributes. The URL
    string that defines the attribute is immutable, as are all of the
    derivative values from this string like authority, name, value, and
    namespace.  The public key and associated KAS url are mutable, as is the
    display name.  AttributeValues are comparable, sortable, and serializable
    to and from dict objects.
    """

    @classmethod
    def from_raw_dict(cls, raw_dict):
        """Construct an AttributeValue from a raw dictionary."""
        logger.debug("Attribute raw dict = %s", raw_dict)

        if "attribute" not in raw_dict:
            logger.error("Attribute property missing in %s", raw_dict)
            raise MalformedAttributeError("Attribute property missing")
        attribute = raw_dict["attribute"]

        key_word_args = {}
        if "kasUrl" in raw_dict:
            key_word_args["kas_url"] = raw_dict["kasUrl"]
        if "pubKey" in raw_dict:
            key_word_args["pub_key"] = raw_dict["pubKey"]
        if "displayName" in raw_dict:
            key_word_args["display_name"] = raw_dict["displayName"]

        if (
            ("isDefault" in raw_dict) and (raw_dict["isDefault"] is True)
        ) or attribute == (eas_config.get_item("DEFAULT_ATTRIBUTE_URL")):
            key_word_args["is_default"] = True
        else:
            key_word_args["is_default"] = False

        logger.debug("Constructing attribute = %s", attribute)
        logger.debug("           with kwargs = %s", key_word_args)

        attr = cls(attribute, **key_word_args)
        if "state" in raw_dict:
            attr.state = raw_dict["state"]
        return attr

    @classmethod
    def from_uri(cls, uri):
        """Construct an attribute from a URI."""
        default_kas_url = eas_config.get_item("KAS_DEFAULT_URL")
        kas_pub_key = (get_key_using_config("KAS_CERTIFICATE"),)
        attr = cls(uri, kas_url=default_kas_url, pub_key=kas_pub_key)
        return attr

    def __init__(
        self,
        attribute: str = None,
        *,
        kas_url: str = None,
        pub_key: str = None,
        display_name: str = None,
        is_default: bool = False,
        algorithm=None,
        state=State.ACTIVE.value,
    ):
        """Initialize with a descriptor string."""
        if not attribute:
            logger.error("No Attribute String")
            raise MalformedAttributeError("No attribute string")
        if not attr_desc_check.match(attribute):
            logger.error("Invalid attribute String = %s", attribute)
            raise MalformedAttributeError(attribute)

        first_splits = attribute.split(ATTR_)
        second_splits = first_splits[1].split(VALUE_)

        # Authority namespace is case insensitive
        self.__authority = first_splits[0].lower()
        # Name and value are case sensitive
        self.__name = second_splits[0]
        self.__value = second_splits[1]

        logger.debug("Attribute Authority = %s", self.__authority)
        logger.debug("Attribute Name  = %s", self.__name)
        logger.debug("Attribute Value     = %s", self.__value)

        if kas_url:
            self.__kas_url = kas_url
        else:
            raise MalformedAttributeError("kas_url is missing")

        if pub_key:
            self.__pub_key = pub_key
        else:
            raise MalformedAttributeError("pub_key is missing")

        if display_name:
            self.__display_name = display_name
        else:
            self.__display_name = f"{self.__name}::{self.__value}"
        logger.debug("Display Name = %s", self.__display_name)

        self.__is_default = bool(is_default)
        logger.debug("Is Default = %s", self.__is_default)

        self.__state = state

    def to_raw_dict(self):
        """Export a raw dict."""
        raw_dict = {
            "attribute": self.attribute,
            "displayName": self.display_name,
            "pubKey": self.pub_key,
            "kasUrl": self.kas_url,
        }
        if self.__is_default:
            raw_dict["isDefault"] = True

        logger.debug("Exporting raw_dict = %s", raw_dict)
        return raw_dict

    def to_jwt(self, private_key, *, algorithm="RS256"):
        """Export a jwt form."""
        # create the JWT
        raw = self.to_raw_dict()
        exp_time = exp_env_to_time(eas_config.get_item("EAS_ENTITY_EXPIRATION"))
        if exp_time is not None:
            raw["exp"] = exp_time
        attr_jwt_bytes = jwt.encode(raw, private_key, algorithm)
        attr_jwt = attr_jwt_bytes.decode("utf-8")

        logger.debug("Exporting jwt = %s", attr_jwt)
        return attr_jwt

    def __eq__(self, other):
        """Compare self to other for equality."""
        return self.attribute == other.attribute

    def __hash__(self):
        """Generate a hash value common between all equal instances."""
        return hash(self.attribute)

    @property
    def attribute(self):
        """Return the full attribute url string."""
        return self.make_uri(self.__authority, self.__name, self.__value)

    @attribute.setter
    def attribute(self, new_url):
        """Do nothing. Read only."""
        pass

    @classmethod
    def make_uri(cls, authority: str, name: str, value: str) -> str:
        return f"{authority}/attr/{name}/value/{value}"

    @property
    def namespace(self):
        """Return the fully defined namespace = authority + name."""
        return f"{self.__authority}/attr/{self.__name}"

    @namespace.setter
    def namespace(self, new_namespace):
        """Do nothing. Read only."""
        pass

    @property
    def authorityNamespace(self):
        """Return only the authority portion of the attribute string."""
        return self.__authority

    @authorityNamespace.setter
    def authorityNamespace(self, new_authority):
        """Do nothing. Read only."""
        pass

    @property
    def name(self):
        """Return the name name of the attribute."""
        return self.__name

    @name.setter
    def name(self, new_name):
        """Do nothing (immutable). Read only."""
        pass

    @property
    def value(self):
        """Return the value portion of the attribute string."""
        return self.__value

    @value.setter
    def value(self, new_value):
        """Do nothing. Read only."""
        pass

    @property
    def display_name(self):
        """Return the display_name for the attribute."""
        return self.__display_name

    @display_name.setter
    def display_name(self, new_name):
        """Do nothing. Read only."""
        pass

    @property
    def pub_key(self):
        """Return the public key for the attribute."""
        return self.__pub_key

    @pub_key.setter
    def pub_key(self, new_key):
        """Do nothing. Read only."""
        pass

    @property
    def kas_url(self):
        """Return the kas url for the attribute."""
        return self.__kas_url

    @kas_url.setter
    def kas_url(self, new_url):
        """Do nothing. Read only."""
        pass

    @property
    def is_default(self):
        """Return the truth without exposing the variable."""
        return self.__is_default is True

    @is_default.setter
    def is_default(self, new_default_flag):
        """Do nothing. Read only."""
        pass

    @property
    def state(self) -> State:
        """Return the id value."""
        return self.__state

    @state.setter
    def state(self, s: State):
        """Validate before setting."""
        state_value = State.from_input(s)
        if state_value:
            self.__state = state_value

    def get_attribute_name(self):
        """Return a newly generated attribute name object for this attribute value.
        Note that rule and order will not be populated."""
        return AttributeName(name=self.name, authorityNamespace=self.authorityNamespace)
