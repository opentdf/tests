"""attribute validation regex."""

import pytest  # noqa: F401

from .validation import url_check
from .validation import attr_url_check
from .validation import attr_desc_check

# ===============  URL TESTS =========================


def test_url_validation_regex_good_value():
    """Test url validation with a good string."""
    test_case = "https://www.example.com"
    actual = url_check.match(test_case)

    assert actual is not None


def test_url_validation_regex_good_value_no_www():
    """Test url validation with a good string."""
    test_case = "https://example.com"
    actual = url_check.match(test_case)

    assert actual is not None


def test_url_validation_regex_good_value_http():
    """Test url validation with a good string."""
    test_case = "http://www.example.com"
    actual = url_check.match(test_case)

    assert actual is not None


def test_url_validation_regex_case_insensitive():
    """Test url validation with mixed case."""
    test_case = "https://www.eXaMple.com/"
    actual = url_check.match(test_case)

    assert actual is not None


def test_url_validation_regex_internal_hyphen():
    """Test url validation."""
    test_case = "https://www.ex-ample.com"
    actual = url_check.match(test_case)

    assert actual is not None


def test_url_validation_regex_multiple_words():
    """Test url validation."""
    test_case = "https://www.exa.mple.com"
    actual = url_check.match(test_case)

    assert actual is not None


def test_url_validation_regex_pass_localhost():
    """Test url validation."""
    test_case = "http://localhost:4000"
    actual = url_check.match(test_case)

    assert actual is not None


def test_url_validation_regex_pass_short_host_with_port():
    """Test url validation."""
    test_case = "http://kas:4000"
    actual = url_check.match(test_case)

    assert actual is not None


def test_url_validation_regex_pass_arbitrary_host_with_port():
    """Test url validation."""
    test_case = "http://some.host.with.port:4000"
    actual = url_check.match(test_case)

    assert actual is not None


def test_url_validation_regex_pass_ip_address():
    """Test url validation."""
    test_case = "http://127.0.0.1:4000"
    actual = url_check.match(test_case)

    assert actual is not None


def test_url_validation_regex_fail_bad_scheme():
    """Test url validation."""
    test_case = "hffps://www.example.com"
    actual = url_check.match(test_case)

    assert actual is None


def test_url_validation_regex_fail_no_colon():
    """Test url validation."""
    test_case = "https//www.exa.mple.com"
    actual = url_check.match(test_case)

    assert actual is None


def test_url_validation_regex_fail_too_few_slashes():
    """Test url validation."""
    test_case = "https:/www.example.com"
    actual = url_check.match(test_case)

    assert actual is None


def test_url_validation_regex_fail_too_many_slashes():
    """Test url validation."""
    test_case = "hffps:///www.example.com"
    actual = url_check.match(test_case)

    assert actual is None


def test_url_validation_regex_fail_terminated_with_one_char():
    """Test url validation."""
    test_case = "hffps://www.example.c"
    actual = url_check.match(test_case)

    assert actual is None


# =============== ATTRIBUTE URL TESTS =========================


def test_attr_url_validation_regex_good_value():
    """Test url validation with a good string."""
    test_case = "https://acme.mil/attr/acmeclassification"
    actual = attr_url_check.match(test_case)

    assert actual is not None


def test_attr_url_validation_regex_case_insensitive():
    """Test url validation with mixed case."""
    test_case = "https://www.example.com/atTR/foO"
    actual = attr_url_check.match(test_case)

    assert actual is not None


def test_attr_url_validation_regex_internal_hyphen():
    """Test url validation with mixed case."""
    test_case = "https://www.ex-ample.com/attr/fo-o"
    actual = attr_url_check.match(test_case)

    assert actual is not None


def test_attr_url_validation_regex_with_no_attrute():
    """Test url validation with a good value."""
    test_case = "https://www.example.com/attr/"
    actual = attr_url_check.match(test_case)

    assert actual is None


def test_attr_url_regex_with_mangled_attr_tag():
    """Test url validation with a good value."""
    test_case = "https://www.example.com/atr/foo"
    actual = attr_url_check.match(test_case)

    assert actual is None


# =============== ATTRIBUTE DESCRIPTOR TESTS =========================


def test_attr_descriptor_validation_regex_with_good_value():
    """Test descriptor validation with a good value."""
    test_case = "https://www.example.com/attr/foo/value/bar"
    test_case = "https://www.example.com/attr/NTK/value/BAR"
    actual = attr_desc_check.match(test_case)

    assert actual is not None


def test_attr_descriptor_validation_regex_case_insensitive():
    """Test descriptor validation with a good value."""
    test_case = "https://www.example.com/attr/foo/VaLUe/bar"
    actual = attr_desc_check.match(test_case)

    assert actual is not None


def test_attr_descriptor_validation_regex_with_bad_value():
    """Test descriptor validation with a good value."""
    test_case = "https://www.example.com/attr/foo/val/bar"
    actual = attr_desc_check.match(test_case)

    assert actual is None


def test_attr_descriptor_validation_regex_with_no_value():
    """Test url validation with a good value."""
    test_case = "https://www.example.com/attr/foo/value/"
    actual = attr_desc_check.match(test_case)

    assert actual is None
