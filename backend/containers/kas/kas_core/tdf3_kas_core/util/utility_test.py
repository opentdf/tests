from .utility import value_to_boolean


def test_value_to_boolean():
    assert value_to_boolean("0") == False
    assert value_to_boolean("FaLsE") == False
    assert value_to_boolean(None) == False
    assert value_to_boolean("1") == False  # Numbers not accepted as true
    assert value_to_boolean("tRuE") == True
    assert value_to_boolean("invalid") == False
    assert value_to_boolean(True) == True
    assert value_to_boolean(False) == False
