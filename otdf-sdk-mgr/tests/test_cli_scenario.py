"""End-to-end smoke test for `otdf-sdk-mgr install scenario`."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from otdf_sdk_mgr.cli_scenario import install_scenario_cmd
from otdf_sdk_mgr.schema import load_scenario, scenario_to_pytest_sdks


SCENARIO_YAML = """
apiVersion: opentdf.io/v1alpha1
kind: Scenario
metadata:
  id: smoke
  title: install-scenario smoke
instance:
  platform: { dist: v0.9.0 }
  kas:
    alpha: { dist: v0.9.0, mode: standard }
sdks:
  encrypt:
    - sdk: go
      version: v0.24.0
    - sdk: js
      version: v0.5.0
  decrypt:
    - sdk: js
      version: v0.5.0
    - sdk: java
      version: v0.7.8
suite:
  targets:
    - "xtest/test_tdfs.py::test_tdf_roundtrip"
"""


def test_install_scenario_writes_consumable_manifest(tmp_path: Path) -> None:
    scenario_path = tmp_path / "s.yaml"
    scenario_path.write_text(SCENARIO_YAML)

    platform_dist = tmp_path / "platform-dist" / "v0.9.0"

    def fake_install_release(sdk: str, version: str) -> Path:
        return tmp_path / "sdk" / sdk / version

    with (
        patch("otdf_sdk_mgr.cli_scenario.install_platform_release", return_value=platform_dist),
        patch("otdf_sdk_mgr.cli_scenario.install_helper_scripts"),
        patch("otdf_sdk_mgr.cli_scenario.install_release", side_effect=fake_install_release),
    ):
        install_scenario_cmd(scenario_path, skip_scripts=False)

    out_path = tmp_path / "s.installed.json"
    record = json.loads(out_path.read_text())

    assert record["platform"] == {
        "kind": "dist",
        "version": "v0.9.0",
        "path": str(platform_dist),
    }
    assert set(record["kas"].keys()) == {"alpha"}
    assert record["kas"]["alpha"]["mode"] == "standard"
    assert record["kas"]["alpha"]["features"] == {}
    assert record["sdks"]["encrypt"] == [
        {
            "sdk": "go",
            "version": "v0.24.0",
            "source": None,
            "path": str(tmp_path / "sdk" / "go" / "v0.24.0"),
        },
        {
            "sdk": "js",
            "version": "v0.5.0",
            "source": None,
            "path": str(tmp_path / "sdk" / "js" / "v0.5.0"),
        },
    ]
    assert record["sdks"]["decrypt"] == [
        {
            "sdk": "js",
            "version": "v0.5.0",
            "source": None,
            "path": str(tmp_path / "sdk" / "js" / "v0.5.0"),
        },
        {
            "sdk": "java",
            "version": "v0.7.8",
            "source": None,
            "path": str(tmp_path / "sdk" / "java" / "v0.7.8"),
        },
    ]
    assert "status" not in record

    # The manifest must be consumable by the downstream reader.
    scenario = load_scenario(scenario_path)
    tokens = scenario_to_pytest_sdks(scenario, out_path)
    assert tokens == {
        "encrypt": ["go@v0.24.0", "js@v0.5.0"],
        "decrypt": ["js@v0.5.0", "java@v0.7.8"],
    }


def test_install_scenario_preserves_kas_mode_and_features(tmp_path: Path) -> None:
    """KasPin.mode and KasPin.features round-trip into installed.json."""
    scenario_yaml = """
apiVersion: opentdf.io/v1alpha1
kind: Scenario
metadata:
  id: km-smoke
instance:
  platform: { dist: v0.9.0 }
  kas:
    alpha:
      dist: v0.9.0
      mode: key_management
      features:
        ec_tdf_enabled: true
        rotation_enabled: false
sdks:
  encrypt:
    - { sdk: go, version: v0.24.0 }
  decrypt:
    - { sdk: go, version: v0.24.0 }
suite:
  targets: ["xtest/test_tdfs.py"]
"""
    scenario_path = tmp_path / "s.yaml"
    scenario_path.write_text(scenario_yaml)
    platform_dist = tmp_path / "platform-dist" / "v0.9.0"

    with (
        patch("otdf_sdk_mgr.cli_scenario.install_platform_release", return_value=platform_dist),
        patch("otdf_sdk_mgr.cli_scenario.install_helper_scripts"),
        patch(
            "otdf_sdk_mgr.cli_scenario.install_release",
            side_effect=lambda sdk, version: tmp_path / "sdk" / sdk / version,
        ),
    ):
        install_scenario_cmd(scenario_path, skip_scripts=True)

    record = json.loads((tmp_path / "s.installed.json").read_text())
    alpha = record["kas"]["alpha"]
    assert alpha["mode"] == "key_management"
    assert alpha["features"] == {"ec_tdf_enabled": True, "rotation_enabled": False}


def test_install_scenario_writes_partial_manifest_on_failure(tmp_path: Path) -> None:
    from otdf_sdk_mgr.installers import InstallError

    scenario_path = tmp_path / "s.yaml"
    scenario_path.write_text(SCENARIO_YAML)
    platform_dist = tmp_path / "platform-dist" / "v0.9.0"

    with (
        patch("otdf_sdk_mgr.cli_scenario.install_platform_release", return_value=platform_dist),
        patch("otdf_sdk_mgr.cli_scenario.install_helper_scripts"),
        patch("otdf_sdk_mgr.cli_scenario.install_release", side_effect=InstallError("boom")),
        pytest.raises(typer.Exit),
    ):
        install_scenario_cmd(scenario_path, skip_scripts=True)

    out_path = tmp_path / "s.installed.json"
    record = json.loads(out_path.read_text())
    assert record["status"] == "partial"
    assert record["platform"] is not None
