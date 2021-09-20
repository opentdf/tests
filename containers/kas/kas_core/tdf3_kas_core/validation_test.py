"""attribute validation regex."""

import pytest  # noqa: F401

from .validation import attr_authority_check
from .validation import attr_namespace_check
from .validation import attr_attribute_check

# ===============  HOST TESTS =========================


def test_host_validation_regex_good_value():
    """Test host validation with a good string."""
    test_case = "https://www.example.com"
    actual = attr_authority_check.match(test_case)
    print(actual)
    assert actual is not None


def test_host_validation_regex_good_value_no_www():
    """Test host validation with a good string."""
    test_case = "https://example.com"
    actual = attr_authority_check.match(test_case)
    print(actual)
    assert actual is not None


def test_host_validation_regex_good_value_http():
    """Test host validation with a good string."""
    test_case = "http://www.example.com"
    actual = attr_authority_check.match(test_case)
    print(actual)
    assert actual is not None


def test_host_validation_regex_case_insensitive():
    """Test host validation with mixed case."""
    test_case = "https://www.eXaMple.com/"
    actual = attr_authority_check.match(test_case)
    print(actual)
    assert actual is not None


def test_host_validation_regex_internal_hyphen():
    """Test host validation."""
    test_case = "https://www.ex-ample.com"
    actual = attr_authority_check.match(test_case)
    print(actual)
    assert actual is not None


def test_host_validation_regex_multiple_words():
    """Test host validation."""
    test_case = "https://www.exa.mple.com"
    actual = attr_authority_check.match(test_case)
    print(actual)
    assert actual is not None


def test_host_validation_regex_pass_localhost():
    """Test host validation."""
    test_case = "http://localhost:4000"
    actual = attr_authority_check.match(test_case)
    print(actual)
    assert actual is not None


def test_host_validation_regex_pass_short_host_with_port():
    """Test host validation."""
    test_case = "http://kas:4000"
    actual = attr_authority_check.match(test_case)
    print(actual)
    assert actual is not None


def test_host_validation_regex_pass_arbitrary_host_with_port():
    """Test host validation."""
    test_case = "http://some.host.with.port:4000"
    actual = attr_authority_check.match(test_case)
    print(actual)
    assert actual is not None


def test_host_validation_regex_pass_ip_address():
    """Test host validation."""
    test_case = "http://127.0.0.1:4000"
    actual = attr_authority_check.match(test_case)
    print(actual)
    assert actual is not None


def test_host_validation_regex_fail_bad_scheme():
    """Test host validation."""
    test_case = "hffps://www.example.com"
    actual = attr_authority_check.match(test_case)
    print(actual)
    assert actual is None


def test_host_validation_regex_fail_no_colon():
    """Test host validation."""
    test_case = "https//www.exa.mple.com"
    actual = attr_authority_check.match(test_case)
    print(actual)
    assert actual is None


def test_host_validation_regex_fail_too_few_slashes():
    """Test host validation."""
    test_case = "https:/www.example.com"
    actual = attr_authority_check.match(test_case)
    print(actual)
    assert actual is None


def test_host_validation_regex_fail_too_many_slashes():
    """Test host validation."""
    test_case = "hffps:///www.example.com"
    actual = attr_authority_check.match(test_case)
    print(actual)
    assert actual is None


def test_host_validation_regex_fail_terminated_with_one_char():
    """Test host validation."""
    test_case = "hffps://www.example.c"
    actual = attr_authority_check.match(test_case)
    print(actual)
    assert actual is None


# =============== ATTRIBUTE NAMESPACE TESTS =========================


def test_attr_namespace_validation_regex_good_value():
    """Test namespace validation with a good string."""
    test_case = "https://acme.mil/attr/acmeclassification"
    actual = attr_namespace_check.match(test_case)
    print(actual)
    assert actual is not None


def test_attr_namespace_validation_regex_case_insensitive():
    """Test namespace validation with mixed case."""
    test_case = "https://www.example.com/atTR/foO"
    actual = attr_namespace_check.match(test_case)
    print(actual)
    assert actual is not None


def test_attr_namespace_validation_regex_internal_hyphen():
    """Test namespace validation with mixed case."""
    test_case = "https://www.ex-ample.com/attr/fo-o"
    actual = attr_namespace_check.match(test_case)
    print(actual)
    assert actual is not None


def test_attr_namespace_validation_regex_with_no_name():
    """Test namespace validation with a good value."""
    test_case = "https://www.example.com/attr/"
    actual = attr_namespace_check.match(test_case)
    print(actual)
    assert actual is None


def test_attr_namespace_regex_with_mangled_attr_tag():
    """Test namespace validation with a good value."""
    test_case = "https://www.example.com/atr/foo"
    actual = attr_namespace_check.match(test_case)
    print(actual)
    assert actual is None


# =============== ATTRIBUTE DESCRIPTOR TESTS =========================


def test_attr_attribute_validation_regex_with_good_value():
    """Test attribute validation with a good value."""
    test_case = "https://www.example.com/attr/foo/value/bar"
    test_case = "https://www.example.com/attr/NTK/value/BAR"
    actual = attr_attribute_check.match(test_case)
    print(actual)
    assert actual is not None


def test_attr_attribute_validation_regex_case_insensitive():
    """Test attribute validation with a good value."""
    test_case = "https://www.example.com/attr/foo/VaLUe/bar"
    actual = attr_attribute_check.match(test_case)
    print(actual)
    assert actual is not None


def test_attr_attribute_validation_regex_with_bad_value():
    """Test attribute validation with a good value."""
    test_case = "https://www.example.com/attr/foo/val/bar"
    actual = attr_attribute_check.match(test_case)
    print(actual)
    assert actual is None


def test_attr_attribute_validation_regex_with_no_value():
    """Test attribute validation with a good value."""
    test_case = "https://www.example.com/attr/foo/value/"
    actual = attr_attribute_check.match(test_case)
    print(actual)
    assert actual is None
