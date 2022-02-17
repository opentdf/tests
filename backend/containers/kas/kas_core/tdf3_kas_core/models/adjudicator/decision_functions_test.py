"""Test the Adjudicator and helper functions."""

import pytest

from tdf3_kas_core.models import AttributeValue
from tdf3_kas_core.models import AttributePolicy

from tdf3_kas_core.errors import AuthorizationError

from .decision_functions import all_of_decision
from .decision_functions import any_of_decision
from .decision_functions import hierarchy_decision

from tdf3_kas_core.models import HIERARCHY


A = AttributeValue("https://www.example.com/attr/test-attr/value/AAA")
B = AttributeValue("https://www.example.com/attr/test-attr/value/BBB")
C = AttributeValue("https://www.example.com/attr/test-attr/value/CCC")
D = AttributeValue("https://www.example.com/attr/test-attr/value/DDD")
E = AttributeValue("https://www.example.com/attr/test-attr/value/EEE")
F = AttributeValue("https://www.example.com/attr/test-attr/value/FFF")
G = AttributeValue("https://www.example.com/attr/test-attr/value/GGG")


AA = AttributeValue("https://www.example.com/attr/test-attr/value/AAA")
BB = AttributeValue("https://www.example.com/attr/test-attr/value/BBB")
CC = AttributeValue("https://www.example.com/attr/test-attr/value/CCC")
DD = AttributeValue("https://www.example.com/attr/test-attr/value/DDD")
EE = AttributeValue("https://www.example.com/attr/test-attr/value/EEE")
FF = AttributeValue("https://www.example.com/attr/test-attr/value/FFF")
GG = AttributeValue("https://www.example.com/attr/test-attr/value/GGG")


# ========== ALL OF ===================


def test_all_of_decision_success_exact_match():
    """Test with equal attribute sets."""
    entity_values = frozenset([A, B])
    data_values = frozenset([AA, BB])
    assert all_of_decision(data_values, entity_values) is True


def test_all_of_decision_success_excess_in_entity():
    """Test with excess values in entity set."""
    entity_values = frozenset([A, B, C, D])
    data_values = frozenset([A, B])
    assert all_of_decision(data_values, entity_values) is True


def test_all_of_decision_success_empty_data_set():
    """Test all_of_decision."""
    entity_values = frozenset([A, B])
    data_values = frozenset([])
    assert all_of_decision(data_values, entity_values) is True


def test_all_of_decision_success_both_sets_empty():
    """Test all_of_decision."""
    entity_values = frozenset([])
    data_values = frozenset([])
    assert all_of_decision(data_values, entity_values) is True


def test_all_of_decision_fail_entity_missing_values():
    """Test all_of_decision."""
    e_val = frozenset([A, B])
    d_val = frozenset([A, B, C, D])
    with pytest.raises(AuthorizationError):
        all_of_decision(d_val, e_val)


def test_all_of_decision_fail_disjoint_sets():
    """Test with equal attribute sets."""
    e_val = frozenset([A, B])
    d_val = frozenset([C, D])
    with pytest.raises(AuthorizationError):
        all_of_decision(d_val, e_val)


def test_all_of_decision_fail_empty_entity_sets():
    """Test all_of_decision."""
    e_val = frozenset([])
    d_val = frozenset([A, B])
    with pytest.raises(AuthorizationError):
        all_of_decision(d_val, e_val)


# ========== ANY OF ===================


def test_any_of_decision_success_entity_has_one():
    """Test any_of_decision."""
    entity_values = frozenset([C])
    data_values = frozenset([A, B, C, D, E, F, G])
    assert any_of_decision(data_values, entity_values) is True


def test_any_of_decision_success_exact_match():
    """Test any_of_decision."""
    entity_values = frozenset([A, B])
    data_values = frozenset([A, B])
    assert any_of_decision(data_values, entity_values) is True


def test_any_of_decision_success_excess_in_entity():
    """Test any_of_decision."""
    entity_values = frozenset([A, B, C, D])
    data_values = frozenset([A, B])
    assert any_of_decision(data_values, entity_values) is True


def test_any_of_decision_success_empty_data_set():
    """Test any_of_decision."""
    entity_values = frozenset([A, B])
    data_values = frozenset([])
    assert any_of_decision(data_values, entity_values) is True


def test_any_of_decision_success_both_sets_empty():
    """Test any_of_decision."""
    entity_values = frozenset([])
    data_values = frozenset([])
    assert any_of_decision(data_values, entity_values) is True


def test_any_of_decision_fail_disjoint_sets():
    """Test any_of_decision."""
    e_val = frozenset([A, B])
    d_val = frozenset([C, D])
    with pytest.raises(AuthorizationError):
        any_of_decision(d_val, e_val)


def test_any_of_decision_fail_empty_entity_sets():
    """Test any_of_decision."""
    e_val = frozenset([])
    d_val = frozenset([A, B])
    with pytest.raises(AuthorizationError):
        any_of_decision(d_val, e_val)


# ========== HIERARCHY ===================

classif_policy = AttributePolicy(
    "https://example.com/attr/classif", HIERARCHY, order=["TS", "S", "C", "U"]
)


def test_hierarchy_decision_success_exact_match():
    """Test hierarchy_decision."""
    eS = AttributeValue("https://www.example.com/attr/CLASSIF/value/TS")
    dS = AttributeValue("https://www.example.com/attr/CLASSIF/value/TS")
    entity_values = frozenset([eS])
    data_values = frozenset([dS])
    assert (
        hierarchy_decision(data_values, entity_values, classif_policy.options["order"])
        is True
    )


def test_hierarchy_decision_success_entity_value_exceeds():
    """Test hierarchy_decision."""
    eS = AttributeValue("https://www.example.com/attr/classif/value/TS")
    dS = AttributeValue("https://www.example.com/attr/classif/value/S")
    entity_values = frozenset([eS])
    data_values = frozenset([dS])
    assert (
        hierarchy_decision(data_values, entity_values, classif_policy.options["order"])
        is True
    )


def test_hierarchy_decision_fail_entity_value_insufficient():
    """Test hierarchy_decision."""
    eS = AttributeValue("https://www.example.com/attr/classif/value/S")
    dS = AttributeValue("https://www.example.com/attr/classif/value/TS")
    entity_values = frozenset([eS])
    data_values = frozenset([dS])
    with pytest.raises(AuthorizationError):
        hierarchy_decision(data_values, entity_values, classif_policy.options["order"])


def test_hierarchy_decision_fail_entity_value_unknown():
    """Test hierarchy_decision."""
    eS = AttributeValue("https://www.example.com/attr/classif/value/huh")
    dS = AttributeValue("https://www.example.com/attr/classif/value/TS")
    entity_values = frozenset([eS])
    data_values = frozenset([dS])
    with pytest.raises(AuthorizationError):
        hierarchy_decision(data_values, entity_values, classif_policy.options["order"])


def test_hierarchy_decision_fail_data_value_unknown():
    """Test hierarchy_decision."""
    eS = AttributeValue("https://www.example.com/attr/classif/value/U")
    dS = AttributeValue("https://www.example.com/attr/classif/value/dude")
    entity_values = frozenset([eS])
    data_values = frozenset([dS])
    with pytest.raises(AuthorizationError):
        hierarchy_decision(data_values, entity_values, classif_policy.options["order"])


def test_hierarchy_decision_fail_data_has_extra_values():
    """Test hierarchy_decision."""
    eS = AttributeValue("https://www.example.com/attr/classif/value/TS")
    dS1 = AttributeValue("https://www.example.com/attr/classif/value/S")
    dS2 = AttributeValue("https://www.example.com/attr/classif/value/TS")
    entity_values = frozenset([eS])
    data_values = frozenset([dS1, dS2])
    with pytest.raises(AuthorizationError):
        hierarchy_decision(data_values, entity_values, classif_policy.options["order"])


def test_hierarchy_decision_fail_entity_has_extra_values():
    """Test hierarchy_decision."""
    eS1 = AttributeValue("https://www.example.com/attr/classif/value/TS")
    eS2 = AttributeValue("https://www.example.com/attr/classif/value/S")
    dS = AttributeValue("https://www.example.com/attr/classif/value/S")
    entity_values = frozenset([eS1, eS2])
    data_values = frozenset([dS])
    with pytest.raises(AuthorizationError):
        hierarchy_decision(data_values, entity_values, classif_policy.options["order"])
