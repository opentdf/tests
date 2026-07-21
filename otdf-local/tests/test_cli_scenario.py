"""Tests for `_build_pytest_args` — the scenario-suite → pytest argv translator."""

from __future__ import annotations

from pathlib import Path

import pytest
from otdf_sdk_mgr.schema import (
    Instance,
    Metadata,
    PlatformPin,
    Scenario,
    ScenarioSdk,
    ScenarioSdks,
    Suite,
)

from otdf_local import cli_scenario


def _scenario(suite: Suite, sdks: ScenarioSdks | None = None) -> Scenario:
    return Scenario(
        metadata=Metadata(name="t"),
        instance=Instance(
            metadata=Metadata(name="t"),
            platform=PlatformPin(dist="v0.9.0"),
        ),
        sdks=sdks or ScenarioSdks(),
        suite=suite,
    )


@pytest.fixture
def stub_sdks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass the installed.json round-trip; tests focus on the suite block."""
    monkeypatch.setattr(
        cli_scenario,
        "scenario_to_pytest_sdks",
        lambda _s, _p: {"encrypt": [], "decrypt": []},
    )


def test_empty_targets(stub_sdks: None) -> None:
    args = cli_scenario._build_pytest_args(_scenario(Suite(targets=[])), Path("s.yaml"))
    assert args == []


def test_multi_target(stub_sdks: None) -> None:
    args = cli_scenario._build_pytest_args(
        _scenario(Suite(targets=["test_a.py", "test_b.py::test_x"])), Path("s.yaml")
    )
    assert args == ["test_a.py", "test_b.py::test_x"]


def test_containers_joined(stub_sdks: None) -> None:
    args = cli_scenario._build_pytest_args(
        _scenario(Suite(targets=["test_pqc.py"], containers=["ztdf", "ztdf-ecwrap"])),
        Path("s.yaml"),
    )
    assert args == ["test_pqc.py", "--containers", "ztdf ztdf-ecwrap"]


def test_no_containers_omits_flag(stub_sdks: None) -> None:
    args = cli_scenario._build_pytest_args(
        _scenario(Suite(targets=["t.py"], containers=[])), Path("s.yaml")
    )
    assert "--containers" not in args


def test_kexpr_forwarded(stub_sdks: None) -> None:
    args = cli_scenario._build_pytest_args(
        _scenario(Suite(targets=["t.py"], kexpr="not slow")), Path("s.yaml")
    )
    assert args == ["t.py", "-k", "not slow"]


def test_markers_and_extra_args(stub_sdks: None) -> None:
    args = cli_scenario._build_pytest_args(
        _scenario(Suite(targets=["t.py"], markers="smoke", extra_args=["-vv", "-x"])),
        Path("s.yaml"),
    )
    assert args == ["t.py", "-m", "smoke", "-vv", "-x"]


def test_sdks_tokens_forwarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli_scenario,
        "scenario_to_pytest_sdks",
        lambda _s, _p: {
            "encrypt": ["go@v0.24.0"],
            "decrypt": ["go@v0.24.0", "java@v0.10.0"],
        },
    )
    args = cli_scenario._build_pytest_args(
        _scenario(
            Suite(targets=["t.py"]),
            sdks=ScenarioSdks(
                encrypt=[ScenarioSdk(sdk="go", version="v0.24.0")],
                decrypt=[
                    ScenarioSdk(sdk="go", version="v0.24.0"),
                    ScenarioSdk(sdk="java", version="v0.10.0"),
                ],
            ),
        ),
        Path("s.yaml"),
    )
    assert args == [
        "t.py",
        "--sdks-encrypt",
        "go@v0.24.0",
        "--sdks-decrypt",
        "go@v0.24.0 java@v0.10.0",
    ]
