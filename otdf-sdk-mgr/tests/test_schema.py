"""Schema smoke tests for Scenario/Instance/Pin models."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from otdf_sdk_mgr.schema import (
    Instance,
    KasPin,
    PlatformPin,
    ScenarioSdks,
    SdkPin,
    SourceRef,
    dump_instance,
    installed_json_for,
    load_instance,
    load_scenario,
    scenario_to_pytest_sdks,
)
from pydantic import ValidationError


def _minimal_scenario_yaml() -> str:
    return """
apiVersion: opentdf.io/v1alpha1
kind: Scenario
metadata:
  id: smoke
  title: "schema smoke"
  created: 2026-05-15
instance:
  metadata: { name: smoke }
  platform: { dist: v0.9.0 }
  ports: { base: 9080 }
  kas:
    alpha: { dist: v0.9.0, mode: standard }
sdks:
  encrypt:
    go: { version: lts }
  decrypt:
    java: { version: "0.7.8" }
suite:
  select: "xtest/test_tdfs.py::test_tdf_roundtrip"
  containers: ztdf
"""


def test_scenario_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_text(_minimal_scenario_yaml(), encoding="utf-8")
    scenario = load_scenario(path)
    assert scenario.kind == "Scenario"
    assert scenario.instance.platform.dist == "v0.9.0"
    assert scenario.instance.ports.base == 9080
    assert "alpha" in scenario.instance.kas
    assert scenario.sdks.encrypt["go"].version == "lts"
    assert scenario.sdks.decrypt["java"].version == "0.7.8"


def test_platform_pin_requires_exactly_one_source() -> None:
    with pytest.raises(ValidationError):
        PlatformPin()  # no fields set
    with pytest.raises(ValidationError):
        PlatformPin(dist="v0.9.0", image="ghcr.io/x:v0.9.0")  # two set
    with pytest.raises(ValidationError):
        PlatformPin(dist="", image="ghcr.io/x:v0.9.0")  # presence, not truthiness


def test_kas_pin_features_pass_through() -> None:
    pin = KasPin(dist="v0.9.0", mode="key_management", features={"ec_tdf_enabled": True})
    assert pin.features["ec_tdf_enabled"] is True


def test_scenario_sdks_union_dedupes_and_prefers_decrypt() -> None:
    sdks = ScenarioSdks(
        encrypt={"go": SdkPin(version="lts")},
        decrypt={"go": SdkPin(version="0.7.8"), "java": SdkPin(version="0.7.8")},
    )
    union = sdks.union()
    assert set(union.keys()) == {"go", "java"}
    assert union["go"].version == "0.7.8"


def test_dump_load_instance_roundtrip(tmp_path: Path) -> None:
    inst = Instance(
        platform=PlatformPin(source=SourceRef(ref="main")),
        kas={"alpha": KasPin(dist="v0.9.0")},
    )
    out = tmp_path / "instance.yaml"
    dump_instance(inst, out)
    loaded = load_instance(out)
    assert loaded.platform.source is not None
    assert loaded.platform.source.ref == "main"
    assert loaded.kas["alpha"].dist == "v0.9.0"


def test_unknown_field_rejected_by_extra_forbid(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "apiVersion: opentdf.io/v1alpha1\nkind: Scenario\nunknown_field: oops\n"
        "instance:\n  platform: { dist: v0.9.0 }\nsuite:\n  select: foo\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_scenario(bad)


def test_unknown_kind_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad-kind.yaml"
    bad.write_text(
        "apiVersion: opentdf.io/v1alpha1\nkind: NotScenario\n"
        "instance:\n  platform: { dist: v0.9.0 }\nsuite:\n  select: foo\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_scenario(bad)


def test_unknown_api_version_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad-version.yaml"
    bad.write_text(
        "apiVersion: opentdf.io/v1beta1\nkind: Scenario\n"
        "instance:\n  platform: { dist: v0.9.0 }\nsuite:\n  select: foo\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_scenario(bad)


def test_installed_json_for_swaps_suffix(tmp_path: Path) -> None:
    assert installed_json_for(tmp_path / "x.yaml") == tmp_path / "x.installed.json"
    assert installed_json_for(tmp_path / "y.yml") == tmp_path / "y.installed.json"
    # No extension on the scenario path → still produces a .installed.json sibling.
    assert installed_json_for(tmp_path / "noext") == tmp_path / "noext.installed.json"


def _write_scenario(tmp_path: Path) -> tuple[Path, Path]:
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(_minimal_scenario_yaml(), encoding="utf-8")
    return scenario_path, installed_json_for(scenario_path)


def test_scenario_to_pytest_sdks_uses_dist_dir_name(tmp_path: Path) -> None:
    scenario_path, installed_path = _write_scenario(tmp_path)
    scenario = load_scenario(scenario_path)
    # Simulate what `otdf-sdk-mgr install scenario` writes: paths whose
    # last segment is the dist-dir name xtest will see under sdk/<lang>/dist/.
    installed_path.write_text(
        json.dumps(
            {
                "manifest": str(scenario_path),
                "sdks": {
                    "go": {"version": "lts", "path": str(tmp_path / "sdk/go/dist/v0.24.0")},
                    "java": {"version": "0.7.8", "path": str(tmp_path / "sdk/java/dist/v0.7.8")},
                },
            }
        )
    )
    out = scenario_to_pytest_sdks(scenario, installed_path)
    assert out == {"encrypt": ["go@v0.24.0"], "decrypt": ["java@v0.7.8"]}


def test_scenario_to_pytest_sdks_missing_installed_raises_with_hint(tmp_path: Path) -> None:
    scenario_path, installed_path = _write_scenario(tmp_path)
    scenario = load_scenario(scenario_path)
    with pytest.raises(FileNotFoundError, match="install scenario"):
        scenario_to_pytest_sdks(scenario, installed_path)


def test_scenario_to_pytest_sdks_missing_sdk_entry_raises(tmp_path: Path) -> None:
    scenario_path, installed_path = _write_scenario(tmp_path)
    scenario = load_scenario(scenario_path)
    # Forget to record `java`'s install — should raise ValueError, not silently drop.
    installed_path.write_text(
        json.dumps(
            {"sdks": {"go": {"version": "lts", "path": str(tmp_path / "sdk/go/dist/v0.24.0")}}}
        )
    )
    with pytest.raises(ValueError, match="java"):
        scenario_to_pytest_sdks(scenario, installed_path)
