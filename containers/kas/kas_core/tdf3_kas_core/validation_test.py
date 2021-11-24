"""attribute validation regex."""

import pytest  # noqa: F401

from .validation import attr_authority_check
from .validation import attr_namespace_check
from .validation import attr_attribute_check

# ===============  HOST TESTS =========================


def test_host_validation_regex_good_value():
    """Test host validation with good strings."""
    assert (
        attr_authority_check.match("http://www.example.com").group("scheme") == "http"
    )
    assert (
        attr_authority_check.match("https://www.example.com").group("scheme") == "https"
    )
    assert (
        attr_authority_check.match("https://example.com").group("host") == "example.com"
    )
    assert (
        attr_authority_check.match("https://eXaMple.com").group("host") == "eXaMple.com"
    )
    assert attr_authority_check.match("http://com").group("host") == "com"
    assert attr_authority_check.match("http://ie").group("name") == "ie"
    assert attr_authority_check.match("https://www.example.com").group("port") is None
    assert attr_authority_check.match("https://www.example.com:1").group("port") == "1"
    assert attr_authority_check.match("https://www.example.com:54321").group("port")
    assert attr_authority_check.match("http://localhost")
    assert attr_authority_check.match("https://localhost:1025").group("port")
    assert (
        attr_authority_check.match("https://127.0.0.1:12").group("name") == "127.0.0.1"
    )
    assert attr_authority_check.match("https://127.0.0.1:12").group("port") == "12"
    assert attr_authority_check.match("https://www.ex-ample.com/kas/path").group("path") == "/kas/path"
    assert attr_authority_check.match("https://www.ex-ample.com/").group("path") == "/"
    assert attr_authority_check.match("https://www.ex-ample.com").group("path") is None


def test_wrong_scheme():
    """Test host validation with a bad string."""
    assert attr_authority_check.match("invalid://www.ex.ample.com") is None


def test_missing_colon():
    assert attr_authority_check.match("http//www.ex.ample.com") is None


def test_missing_slash():
    assert attr_authority_check.match("http:/localhost") is None


def test_host_validation_regex_fail_too_many_slashes():
    """Test host validation."""
    assert attr_authority_check.match("http:///localhost") is None


def test_host_validation_regex_fail_terminated_with_one_char():
    """Test host validation."""
    assert attr_authority_check.match("http://a") is None
    assert attr_authority_check.match("http://example.a") is None


# =============== ATTRIBUTE NAMESPACE TESTS =========================
def test_attr_namespace_validation_regex_good_value():
    """Test namespace validation with a good string."""
    assert (
        attr_namespace_check.match("https://acme.mil/attr/acmeclassification").group(
            "namespace"
        )
        == "acmeclassification"
    )

def test_attr_namespace_validation_regex_with_internal_path():
    """Test namespace validation with a good string."""
    assert (
        attr_namespace_check.match("https://acme.mil/kas/attr/acmeclassification").group(
            "namespace"
        )
        == "acmeclassification"
    )


def test_attr_namespace_validation_regex_case_insensitive():
    """Test namespace validation with mixed case."""
    assert (
        attr_namespace_check.match("https://www.example.com/atTR/foO").group(
            "namespace"
        )
        == "foO"
    )


def test_attr_namespace_validation_regex_internal_hyphen():
    """Test namespace validation with mixed case."""
    assert (
        attr_namespace_check.match("https://www.ex-ample.com/attr/fo-o").group(
            "namespace"
        )
        == "fo-o"
    )


def test_attr_namespace_validation_regex_with_no_name():
    """Test namespace validation with a bad value."""
    assert attr_namespace_check.match("https://www.example.com/attr/") is None


def test_attr_namespace_regex_with_mangled_attr_tag():
    """Test namespace validation with a bad value."""
    assert attr_namespace_check.match("https://www.example.com/atr/foo") is None


# =============== ATTRIBUTE DESCRIPTOR TESTS =========================


def test_attr_attribute_validation_regex_with_good_value():
    """Test attribute validation with a good value."""
    assert (
        attr_attribute_check.match("https://www.example.com/attr/foo/value/bar").group(
            "value"
        )
        == "bar"
    )
    assert (
        attr_attribute_check.match("https://www.example.com/attr/NTK/value/BAR").group(
            "value"
        )
        == "BAR"
    )
    assert (
        attr_attribute_check.match(
            "https://example.com/attr/Classification/value/S"
        ).group("namespace")
        == "Classification"
    )
    assert (
        attr_attribute_check.match(
            "https://www.example.com/attr/test-attr/value/AAA"
        ).group("name")
        == "www.example.com"
    )
    assert attr_attribute_check.match(
        "https://example.com/attr/Classification/value/TS"
    )


def test_attr_attribute_validation_regex_case_insensitive():
    """Test attribute validation with a good value."""
    assert attr_attribute_check.match("https://www.example.com/attr/foo/VaLUe/bar")


def test_attr_attribute_validation_regex_with_bad_value():
    """Test attribute validation with bad good value."""
    assert (
        attr_attribute_check.match("https://www.example.com/attr/foo/val/bar") is None
    )


def test_attr_attribute_validation_regex_with_no_value():
    """Test attribute validation with a bad value."""
    assert attr_attribute_check.match("https://www.example.com/attr/foo/value/") is None
