"""Tests for the YAML helpers' failure modes.

Service start() catches (OSError, ValueError) to turn a bad config into a
`start_error`; these pin that every config problem arrives as one of those,
naming the file.
"""

from pathlib import Path

import pytest

from otdf_local.utils.yaml import load_yaml, save_yaml, set_nested


def test_invalid_yaml_is_a_value_error_naming_the_file(tmp_path: Path):
    path = tmp_path / "broken.yaml"
    path.write_text("services: [unclosed\n")

    with pytest.raises(ValueError) as excinfo:
        load_yaml(path)
    assert str(path) in str(excinfo.value)


def test_save_leaves_no_partial_file_behind(tmp_path: Path):
    path = tmp_path / "out.yaml"
    save_yaml(path, {"a": 1})

    assert load_yaml(path) == {"a": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["out.yaml"]


def test_set_nested_fills_in_a_null_intermediate():
    # `preview:` with nothing under it loads as None.
    data: dict = {"services": {"kas": {"preview": None}}}
    set_nested(data, "services.kas.preview.ec_tdf_enabled", True)

    assert data["services"]["kas"]["preview"] == {"ec_tdf_enabled": True}


def test_set_nested_through_a_scalar_is_a_value_error():
    data: dict = {"services": {"kas": "oops"}}

    with pytest.raises(ValueError, match=r"services\.kas is a str"):
        set_nested(data, "services.kas.root_key", "k")
