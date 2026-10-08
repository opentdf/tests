"""Tests for the benchmark environment `otdf-local env` exports.

The contract under test is cross-package: `otdf-sdk-mgr` writes the manifest,
`otdf-local` turns it into environment variables, and `xtest/conftest.py`
consumes them. Nothing in the type system connects those three, so the shape is
asserted here explicitly -- in particular that `OTDFCTL_HEADS` survives the
`json.loads` in `conftest.load_otdfctl`, which is the failure mode that hides:
an unparseable value is discarded silently and the run falls back to an
unpinned CLI while still reporting success.
"""

import json
from pathlib import Path

from otdf_local.cli import bench_manifest_env, bench_manifest_path


def _write_manifest(
    path: Path, otdfctl: dict[str, object] | None, **rest: object
) -> Path:
    manifest: dict[str, object] = {
        "schema_version": "v1alpha1",
        "platform": None,
        "otdfctl": otdfctl,
        "sdk_arms": [],
        "status": "success",
        "status_message": "",
        **rest,
    }
    path.write_text(json.dumps(manifest))
    return path


def _identity(alias: str, tag: str, method: str) -> dict[str, object]:
    return {
        "requested_alias": alias,
        "repository": "https://github.com/opentdf/otdfctl.git",
        "commit_sha": "0" * 40,
        "installed_tag": tag,
        "installed_path": f"/dist/{tag}",
        "installation_method": method,
        "build_settings": {},
    }


class TestBenchManifestPath:
    def test_matches_the_sdk_manager_default(self, tmp_path: Path):
        # Kept in step with otdf_sdk_mgr.bench_prepare.default_manifest_path,
        # which is get_sdk_dir() / "benchmark.installed.json" where get_sdk_dir
        # is <xtest>/sdk.
        assert (
            bench_manifest_path(tmp_path)
            == tmp_path / "sdk" / "benchmark.installed.json"
        )


class TestBenchManifestEnv:
    def test_no_manifest_exports_nothing(self, tmp_path: Path):
        assert bench_manifest_env(tmp_path / "absent.json") == {}

    def test_manifest_pointer_is_absolute(self, tmp_path: Path):
        path = _write_manifest(tmp_path / "m.json", None)
        env = bench_manifest_env(path)
        assert Path(env["BENCH_INSTALLATION_MANIFEST"]).is_absolute()

    def test_otdfctl_heads_is_json_conftest_can_parse(self, tmp_path: Path):
        path = _write_manifest(
            tmp_path / "m.json", _identity("pr:123", "refs--pull--123--head", "source")
        )
        env = bench_manifest_env(path)
        # The exact parse conftest.load_otdfctl performs.
        assert json.loads(env["OTDFCTL_HEADS"]) == ["refs--pull--123--head"]

    def test_released_pin_is_exported_too(self, tmp_path: Path):
        # A release pin that is not exported silently reinstates the
        # dist/main fallback for a run that explicitly asked for a pin.
        path = _write_manifest(
            tmp_path / "m.json", _identity("v0.24.0", "v0.24.0", "release")
        )
        env = bench_manifest_env(path)
        assert json.loads(env["OTDFCTL_HEADS"]) == ["v0.24.0"]

    def test_measured_arms_never_supply_otdfctl(self, tmp_path: Path):
        # The provisioning CLI is pinned separately from the arms under
        # measurement; an arm must not become the tool that provisions it.
        path = _write_manifest(
            tmp_path / "m.json",
            None,
            sdk_arms=[
                _identity("main", "main", "source"),
                _identity("v0.29.0", "v0.29.0", "release"),
            ],
        )
        env = bench_manifest_env(path)
        assert "OTDFCTL_HEADS" not in env
        assert "BENCH_INSTALLATION_MANIFEST" in env

    def test_unreadable_manifest_warns_without_exporting_heads(
        self, tmp_path: Path, capsys
    ):
        path = tmp_path / "m.json"
        path.write_text("{not json")
        env = bench_manifest_env(path)
        assert "OTDFCTL_HEADS" not in env
        # Still points at the manifest so the failure is diagnosable.
        assert "BENCH_INSTALLATION_MANIFEST" in env
        assert "OTDFCTL_HEADS" in capsys.readouterr().out

    def test_pin_without_a_tag_exports_nothing(self, tmp_path: Path):
        # An empty tag would build the path sdk/go/dist//otdfctl.sh.
        path = _write_manifest(tmp_path / "m.json", _identity("main", "", "source"))
        assert "OTDFCTL_HEADS" not in bench_manifest_env(path)
