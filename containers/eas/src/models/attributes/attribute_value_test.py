"""Test AttributeValue."""

import jwt
import pytest

from .attribute_value import AttributeValue
from ...eas_config import EASConfig
from ...errors import MalformedAttributeError
from ...util import get_private_key_from_disk, get_public_key_from_disk

KAS_EXAMPLE_COM = "https://kas.example.com"

SUPER_SECRET_STRING = "super secret string"

KAS_ACME_COM = "https://kas.acme.com"
EXAMPLE_COM = "https://www.example.com"
ANVIL_PROJECT = "Acme Anvil Project"
DEFAULT_NAMESPACE = EASConfig.get_instance().get_item("DEFAULT_NAMESPACE")
ATTRIBUTE_URL_BAR = "https://www.example.com/attr/Foo/value/Bar"
KAS_URL_FOR_TEST = "no:where"


def test_attribute_value_constructor_with_valid_descriptor():
    """Test constructor."""
    actual = AttributeValue(
        "https://wwW.examplE.com/attr/FoO/value/BaR",
        kas_url=KAS_URL_FOR_TEST,
        pub_key=SUPER_SECRET_STRING,
    )
    assert isinstance(actual, AttributeValue)
    # Authority namespace is lower case (case insensitive)
    assert actual.authorityNamespace == actual.authorityNamespace.lower()
    # name and value preserve case
    assert actual.name == "FoO"
    assert actual.value == "BaR"


def test_attribute_value_constructor_with_no_descriptor():
    """Test constructor."""
    with pytest.raises(MalformedAttributeError):
        AttributeValue()


# TODO - add equality and hash tests


# This test is just to make sure the descriptor_validator is installed.
# More detailed descriptor checking tests are found in validation_regex.
def test_descriptor_validation_regex_with_no_value():
    """Test constructor."""
    with pytest.raises(MalformedAttributeError):
        AttributeValue("https://www.example.com/attr/Foo/value/")


# ===== Getters and Setters ==========


def test_attribute_value_full_attribute_getter():
    """Test getter."""
    actual = AttributeValue(
        ATTRIBUTE_URL_BAR, kas_url=KAS_URL_FOR_TEST, pub_key=SUPER_SECRET_STRING
    )
    # Note the case changes.  Standard form is lower case.
    assert actual.attribute == ATTRIBUTE_URL_BAR


def test_attribute_value_full_attribute_setter():
    """Test do-nothing setter."""
    actual = AttributeValue(
        ATTRIBUTE_URL_BAR, kas_url=KAS_URL_FOR_TEST, pub_key=SUPER_SECRET_STRING
    )
    actual.attribute = "Betty Lou Bioloski"
    assert actual.attribute == ATTRIBUTE_URL_BAR


def test_attribute_value_namespace_getter():
    """Test getter."""
    actual = AttributeValue(
        ATTRIBUTE_URL_BAR, kas_url=KAS_URL_FOR_TEST, pub_key=SUPER_SECRET_STRING
    )
    assert actual.namespace == "https://www.example.com/attr/Foo"
    assert actual.authorityNamespace == "https://www.example.com"


def test_attribute_value_namespace_setter():
    """Test constructor."""
    actual = AttributeValue(
        ATTRIBUTE_URL_BAR, kas_url=KAS_URL_FOR_TEST, pub_key=SUPER_SECRET_STRING
    )
    actual.namespace = "Betty Lou Bioloski"
    assert actual.namespace == "https://www.example.com/attr/Foo"
    assert actual.authorityNamespace == "https://www.example.com"


def test_attribute_value_authority_getter():
    """Test constructor."""
    actual = AttributeValue(
        ATTRIBUTE_URL_BAR, kas_url=KAS_URL_FOR_TEST, pub_key=SUPER_SECRET_STRING
    )
    assert actual.authorityNamespace == EXAMPLE_COM


def test_attribute_value_authority_setter():
    """Test do-nothing setter."""
    actual = AttributeValue(
        ATTRIBUTE_URL_BAR,
        kas_url=KAS_EXAMPLE_COM,
        pub_key=SUPER_SECRET_STRING,
    )
    actual.authority = "https://www.acme.com"
    assert actual.authorityNamespace == EXAMPLE_COM


def test_attribute_value_name_getter():
    """Test constructor."""
    actual = AttributeValue(
        ATTRIBUTE_URL_BAR, kas_url=KAS_URL_FOR_TEST, pub_key=SUPER_SECRET_STRING
    )
    assert actual.name == "Foo"


def test_attribute_value_name_setter():
    """Test do-nothing setter."""
    actual = AttributeValue(
        ATTRIBUTE_URL_BAR, kas_url=KAS_URL_FOR_TEST, pub_key=SUPER_SECRET_STRING
    )
    actual.name = "something other than foo"
    assert actual.name == "Foo"


def test_attribute_value_value_getter():
    """Test constructor."""
    actual = AttributeValue(
        ATTRIBUTE_URL_BAR,
        kas_url=KAS_EXAMPLE_COM,
        pub_key=SUPER_SECRET_STRING,
    )
    assert actual.value == "Bar"


def test_attribute_value_value_setter():
    """Test do-nothing setter."""
    actual = AttributeValue(
        ATTRIBUTE_URL_BAR,
        kas_url=KAS_EXAMPLE_COM,
        pub_key=SUPER_SECRET_STRING,
    )
    actual.value = "something other than bar"
    assert actual.value == "Bar"


def test_attribute_value_diplay_name_getter():
    """Test getter."""
    actual = AttributeValue(
        ATTRIBUTE_URL_BAR,
        kas_url=KAS_URL_FOR_TEST,
        pub_key=SUPER_SECRET_STRING,
        display_name="foo:bar",
    )
    assert actual.display_name == "foo:bar"


def test_attribute_value_display_name_setter():
    """Test do-nothing setter."""
    actual = AttributeValue(
        ATTRIBUTE_URL_BAR,
        kas_url=KAS_URL_FOR_TEST,
        pub_key=SUPER_SECRET_STRING,
        display_name="foo:bar",
    )
    actual.display_name = "something other name"
    assert actual.display_name == "foo:bar"


def test_attribute_value_pub_key_getter():
    """Test constructor."""
    actual = AttributeValue(
        ATTRIBUTE_URL_BAR, kas_url=KAS_URL_FOR_TEST, pub_key=SUPER_SECRET_STRING
    )
    assert actual.pub_key == SUPER_SECRET_STRING


def test_attribute_value_pub_keysetter():
    """Test do-nothing setter."""
    actual = AttributeValue(
        ATTRIBUTE_URL_BAR, kas_url=KAS_URL_FOR_TEST, pub_key=SUPER_SECRET_STRING
    )
    actual.pub_key = "a bogus secret string"
    assert actual.pub_key == SUPER_SECRET_STRING


def test_attribute_value_kas_url_getter():
    """Test getter."""
    actual = AttributeValue(
        ATTRIBUTE_URL_BAR,
        kas_url=KAS_EXAMPLE_COM,
        pub_key=SUPER_SECRET_STRING,
    )
    assert actual.kas_url == KAS_EXAMPLE_COM


def test_attribute_value_kas_url_setter():
    """Test do-nothing setter."""
    actual = AttributeValue(
        ATTRIBUTE_URL_BAR,
        kas_url=KAS_EXAMPLE_COM,
        pub_key=SUPER_SECRET_STRING,
    )
    actual.kas_url = "something else"
    assert actual.kas_url == KAS_EXAMPLE_COM


# ========= Comparison methods ==================


def test_attribute_value_equal():
    """Test constructor."""
    v1 = AttributeValue(
        ATTRIBUTE_URL_BAR,
        kas_url=KAS_EXAMPLE_COM,
        pub_key=SUPER_SECRET_STRING,
    )
    v2 = AttributeValue(
        ATTRIBUTE_URL_BAR,
        kas_url=KAS_EXAMPLE_COM,
        pub_key=SUPER_SECRET_STRING,
    )
    assert v1 == v2


def test_namespace_equal_case_insensitive():
    """Test constructor."""
    v1 = AttributeValue(
        "https://www.exaMPle.com/attr/fOO/value/bAr",
        kas_url=KAS_EXAMPLE_COM,
        pub_key=SUPER_SECRET_STRING,
    )
    v2 = AttributeValue(
        "https://www.EXample.com/attr/fOO/value/bAr",
        kas_url=KAS_EXAMPLE_COM,
        pub_key=SUPER_SECRET_STRING,
    )
    assert v1 == v2


# ============ From Raw =====================


def test_attribute_value_from_raw_dict():
    """Test importer."""
    name = "Projects"
    value = "Anvil"

    namespace = f"{DEFAULT_NAMESPACE}/attr/{name}"
    attribute = f"{namespace}/value/{value}"

    display_name = ANVIL_PROJECT
    pub_key = get_public_key_from_disk("test", as_pem=True)
    kas_url = KAS_ACME_COM

    raw = {
        "attribute": attribute,
        "displayName": display_name,
        "pubKey": pub_key,
        "kasUrl": kas_url,
    }

    actual = AttributeValue.from_raw_dict(raw)

    assert isinstance(actual, AttributeValue)
    assert actual.authorityNamespace == DEFAULT_NAMESPACE.lower()
    assert actual.name == name
    assert actual.value == value
    assert actual.display_name == display_name
    assert actual.pub_key == pub_key
    assert actual.kas_url == kas_url
    assert actual.is_default is False


def test_attribute_value_from_raw_dict_is_default():
    """Test importer."""
    name = "Projects"
    value = "Anvil"

    namespace = f"{DEFAULT_NAMESPACE}/attr/{name}"
    attribute = f"{namespace}/value/{value}"

    display_name = ANVIL_PROJECT
    pub_key = get_public_key_from_disk("test", as_pem=True)
    kas_url = KAS_ACME_COM

    raw = {
        "attribute": attribute,
        "displayName": display_name,
        "pubKey": pub_key,
        "kasUrl": kas_url,
        "isDefault": True,
    }

    actual = AttributeValue.from_raw_dict(raw)

    assert isinstance(actual, AttributeValue)
    assert actual.attribute == attribute
    assert actual.authorityNamespace == DEFAULT_NAMESPACE.lower()
    assert actual.name == name
    assert actual.value == value
    assert actual.display_name == display_name
    assert actual.pub_key == pub_key
    assert actual.kas_url == kas_url
    assert actual.is_default is True


def test_attribute_value_to_raw_dict():
    """Test exporter."""
    authority = DEFAULT_NAMESPACE
    name = "Projects"
    value = "Anvil"

    namespace = f"{authority}/attr/{name}"
    attribute = f"{namespace}/value/{value}"

    display_name = ANVIL_PROJECT
    pub_key = get_public_key_from_disk("test", as_pem=True)
    kas_url = KAS_ACME_COM

    raw = {
        "attribute": attribute,
        "displayName": display_name,
        "pubKey": pub_key,
        "kasUrl": kas_url,
    }

    test_case = AttributeValue.from_raw_dict(raw)
    actual = test_case.to_raw_dict()

    assert actual["attribute"] == attribute
    assert actual["displayName"] == display_name
    assert actual["pubKey"] == pub_key
    assert actual["kasUrl"] == kas_url
    assert "isDefault" not in actual


def test_attribute_value_to_raw_dict_is_default():
    """Test exporter."""
    authority = DEFAULT_NAMESPACE
    name = "Projects"
    value = "Anvil"

    namespace = f"{authority}/attr/{name}"
    attribute = f"{namespace}/value/{value}"

    display_name = ANVIL_PROJECT
    pub_key = get_public_key_from_disk("test", as_pem=True)
    kas_url = KAS_ACME_COM

    raw = {
        "attribute": attribute,
        "displayName": display_name,
        "pubKey": pub_key,
        "kasUrl": kas_url,
        "isDefault": True,
    }

    test_case = AttributeValue.from_raw_dict(raw)
    actual = test_case.to_raw_dict()

    assert actual["attribute"] == attribute
    assert actual["displayName"] == display_name
    assert actual["pubKey"] == pub_key
    assert actual["kasUrl"] == kas_url
    assert actual["isDefault"] is True


def test_attribute_value_to_jwt():
    """Test exporter."""
    authority = DEFAULT_NAMESPACE
    name = "Projects"
    value = "Anvil"

    namespace = f"{authority}/attr/{name}"
    attribute = f"{namespace}/value/{value}"

    display_name = ANVIL_PROJECT
    pub_key = get_public_key_from_disk("test", as_pem=True)
    priv_key = get_private_key_from_disk("test", as_pem=True)

    kas_url = KAS_ACME_COM

    expected = AttributeValue.from_raw_dict(
        {
            "attribute": attribute,
            "displayName": display_name,
            "pubKey": pub_key,
            "kasUrl": kas_url,
        }
    )

    actual_jwt = expected.to_jwt(priv_key)

    actual = jwt.decode(actual_jwt, str.encode(pub_key), algorithms=["RS256"])

    assert actual["attribute"] == expected.attribute
    assert actual["displayName"] == expected.display_name
    assert actual["pubKey"] == expected.pub_key
    assert actual["displayName"] == expected.display_name
    assert "isDefault" not in actual


def test_attribute_value_to_jwt_is_default():
    """Test exporter."""
    authority = DEFAULT_NAMESPACE
    name = "Projects"
    value = "Anvil"

    namespace = f"{authority}/attr/{name}"
    attribute = f"{namespace}/value/{value}"

    display_name = ANVIL_PROJECT
    pub_key = get_public_key_from_disk("test", as_pem=True)
    priv_key = get_private_key_from_disk("test", as_pem=True)

    kas_url = KAS_ACME_COM

    expected = AttributeValue.from_raw_dict(
        {
            "attribute": attribute,
            "displayName": display_name,
            "pubKey": pub_key,
            "kasUrl": kas_url,
            "isDefault": True,
        }
    )

    actual_jwt = expected.to_jwt(priv_key)

    actual = jwt.decode(actual_jwt, str.encode(pub_key), algorithms=["RS256"])

    assert actual["attribute"] == expected.attribute
    assert actual["displayName"] == expected.display_name
    assert actual["pubKey"] == expected.pub_key
    assert actual["displayName"] == expected.display_name
    assert actual["isDefault"] is True
