"""Unit tests for the orchestrator's pure-logic pieces.

Subprocess-touching helpers (`ensure_worktree`, `run_cell`) are exercised by
the smoke test in the project root; here we focus on parsing, topological
sorting, cycle detection, and pure path resolution.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from otdf_sdk_mgr.cli_orchestrate import (
    Cell,
    FeatureSpec,
    load_spec,
    topological_waves,
    worktree_for,
)


def _minimal_spec_yaml() -> str:
    return """\
apiVersion: opentdf.io/v1alpha1
kind: Feature
metadata:
  name: ecdsa_binding
  jira: TEST-1
  title: "ECDSA cross-SDK"
  created: 2026-05-18
repos:
  tests:
    branch: TEST-1-tdd
    todo: [register entry]
  platform-proto:
    path: platform
    branch: TEST-1-proto
    todo: [add RPC]
  platform-service:
    path: platform
    branch: TEST-1-service
    depends_on: [platform-proto]
    todo: [impl rewrap]
  java-sdk:
    path: java-sdk
    branch: TEST-1
    depends_on: [platform-proto]
    todo: [impl encrypt]
scenarios:
  - xtest/scenarios/test-1.yaml
"""


def _write_spec(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "feature.yaml"
    p.write_text(body, encoding="utf-8")
    return p


# ----------------------------------------------------------------- load_spec


def test_load_spec_roundtrip(tmp_path: Path) -> None:
    spec = load_spec(_write_spec(tmp_path, _minimal_spec_yaml()))
    assert spec.name == "ecdsa_binding"
    assert spec.jira == "TEST-1"
    assert spec.title == "ECDSA cross-SDK"
    assert set(spec.cells) == {"tests", "platform-proto", "platform-service", "java-sdk"}
    assert spec.cells["platform-service"].depends_on == ("platform-proto",)
    assert spec.cells["tests"].path is None
    assert spec.cells["platform-proto"].path == "platform"
    assert spec.scenarios == ("xtest/scenarios/test-1.yaml",)


def test_load_spec_requires_path_for_non_tests(tmp_path: Path) -> None:
    body = """\
apiVersion: opentdf.io/v1alpha1
kind: Feature
metadata: { name: x, jira: T-1, title: t, created: 2026-05-18 }
repos:
  platform-proto:
    branch: T-1-proto
    todo: []
"""
    with pytest.raises(ValueError, match="path is required"):
        load_spec(_write_spec(tmp_path, body))


def test_load_spec_rejects_unknown_dep(tmp_path: Path) -> None:
    body = """\
apiVersion: opentdf.io/v1alpha1
kind: Feature
metadata: { name: x, jira: T-1, title: t, created: 2026-05-18 }
repos:
  a:
    path: platform
    branch: T-1-a
    depends_on: [b]
    todo: []
"""
    with pytest.raises(ValueError, match="unknown key 'b'"):
        load_spec(_write_spec(tmp_path, body))


# ---------------------------------------------------------- topological_waves


def _cell(key: str, deps: tuple[str, ...] = ()) -> Cell:
    return Cell(key=key, path="x", branch=f"b-{key}", todo=(), depends_on=deps)


def test_topo_no_deps_single_wave() -> None:
    cells = {k: _cell(k) for k in ("a", "b", "c")}
    waves = topological_waves(cells)
    assert len(waves) == 1
    assert sorted(c.key for c in waves[0]) == ["a", "b", "c"]


def test_topo_proto_blocks_rest() -> None:
    cells = {
        "platform-proto": _cell("platform-proto"),
        "platform-service": _cell("platform-service", ("platform-proto",)),
        "java-sdk": _cell("java-sdk", ("platform-proto",)),
        "web-sdk": _cell("web-sdk", ("platform-proto",)),
    }
    waves = topological_waves(cells)
    assert [sorted(c.key for c in w) for w in waves] == [
        ["platform-proto"],
        ["java-sdk", "platform-service", "web-sdk"],
    ]


def test_topo_skip_treats_as_done() -> None:
    cells = {
        "tests": _cell("tests"),
        "platform-proto": _cell("platform-proto", ("tests",)),
    }
    waves = topological_waves(cells, skip={"tests"})
    assert [c.key for w in waves for c in w] == ["platform-proto"]


def test_topo_cycle_detected() -> None:
    cells = {
        "a": _cell("a", ("b",)),
        "b": _cell("b", ("a",)),
    }
    with pytest.raises(ValueError, match="cycle"):
        topological_waves(cells)


def test_topo_diamond() -> None:
    # a → b, a → c, b → d, c → d
    cells = {
        "a": _cell("a"),
        "b": _cell("b", ("a",)),
        "c": _cell("c", ("a",)),
        "d": _cell("d", ("b", "c")),
    }
    waves = topological_waves(cells)
    assert [sorted(c.key for c in w) for w in waves] == [["a"], ["b", "c"], ["d"]]


# ---------------------------------------------------------------- worktree_for


def test_worktree_for_uses_jira_key(tmp_path: Path) -> None:
    spec = load_spec(_write_spec(tmp_path, _minimal_spec_yaml()))
    wt = worktree_for(spec, spec.cells["platform-proto"])
    assert wt.name == "TEST-1-platform-proto"
    assert wt.parent.name == "worktrees"


def test_worktree_for_falls_back_to_name_when_no_jira(tmp_path: Path) -> None:
    body = """\
apiVersion: opentdf.io/v1alpha1
kind: Feature
metadata: { name: ad_hoc, title: t, created: 2026-05-18 }
repos:
  platform-proto:
    path: platform
    branch: ad-hoc-proto
    todo: []
"""
    spec = load_spec(_write_spec(tmp_path, body))
    wt = worktree_for(spec, spec.cells["platform-proto"])
    assert wt.name == "ad_hoc-platform-proto"
