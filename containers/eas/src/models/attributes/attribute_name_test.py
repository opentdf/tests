import pytest

from .attribute_name import AttributeName
from .rule_type import RuleType
from ..state import State
from ...errors import MalformedAttributeError

NAME2 = "name2"

NAME1 = "name1"

EXAMPLE_COM = "https://example.com"


def test_attribute_name():
    # Test constructor
    name1 = AttributeName(
        NAME1,
        authorityNamespace=EXAMPLE_COM,
        order=["one", "two", "three"],
        rule=RuleType.HIERARCHY,
        state=State.ACTIVE,
    )
    assert name1.state == State.ACTIVE
    assert name1.name == NAME1
    assert name1.authorityNamespace == EXAMPLE_COM
    assert name1.rule == RuleType.HIERARCHY

    # Name and authority namespace are immutable
    name1.authorityNamespace = "https://something.new.com"
    assert name1.authorityNamespace == EXAMPLE_COM
    name1.name = "changed_my_mind"
    assert name1.name == NAME1

    # Can change state after creation
    name1.state = State.INACTIVE
    assert name1.state == State.INACTIVE
    # Can change state using the numeric values
    name1.state = 1
    assert name1.state == State.ACTIVE
    name1.state = 2
    assert name1.state == State.INACTIVE
    with pytest.raises(ValueError):
        name1.state = 3
    with pytest.raises(KeyError):
        name1.state = "DELETED"


def test_attribute_name_from_raw():
    name2_raw = {
        "name": NAME2,
        "authorityNamespace": EXAMPLE_COM,
        "rule": RuleType.ANY_OF.to_string(),
        "order": [],
        "state": State.INACTIVE.to_string(),
    }
    name2 = AttributeName.from_raw_dict(name2_raw)
    assert name2.name == NAME2
    assert name2.authorityNamespace == EXAMPLE_COM
    assert name2.rule == RuleType.ANY_OF
    assert name2.state == State.INACTIVE

    name2_raw_again = name2.to_raw_dict()
    for p in ["name", "state", "authorityNamespace", "rule", "order"]:
        assert name2_raw_again[p] == name2_raw[p]

    with pytest.raises(MalformedAttributeError):
        AttributeName.from_raw_dict(
            {
                "authorityNamespace": EXAMPLE_COM,
                "rule": RuleType.ANY_OF.name,
                "order": [],
                "state": State.INACTIVE.value,
            }
        )

    with pytest.raises(MalformedAttributeError):
        AttributeName.from_raw_dict({"name": "some_name", "rule": RuleType.ANY_OF.name})


def test_attribute_name_from_uri():
    name3 = AttributeName.from_uri("https://example.com/attr/name3")
    assert name3.name == "name3"
    assert name3.authorityNamespace == EXAMPLE_COM
    # These are the default values:
    assert name3.rule == RuleType.ALL_OF
    assert name3.state == State.ACTIVE
    assert name3.order == []
