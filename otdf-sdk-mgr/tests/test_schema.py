"""Schema smoke tests for Scenario/Instance/Pin models."""

from __future__ import annotations

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
    load_instance,
    load_scenario,
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
