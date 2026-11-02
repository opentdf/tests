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
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from otdf_local import cli
from otdf_local.cli import bench_manifest_env, bench_manifest_path
from otdf_local.config.settings import Settings


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
        # On stderr: stdout is eval'd.
        out, err = capsys.readouterr()
        assert out == ""
        assert "OTDFCTL_HEADS" in err

    def test_pin_without_a_tag_exports_nothing(self, tmp_path: Path):
        # An empty tag would build the path sdk/go/dist//otdfctl.sh.
        path = _write_manifest(tmp_path / "m.json", _identity("main", "", "source"))
        assert "OTDFCTL_HEADS" not in bench_manifest_env(path)


class _StoppedPlatform:
    def is_running(self) -> bool:
        return False


def _prepare(kind: str, xtest_root: Path) -> None:
    """Leave the manifest `env` will find in the state named by `kind`."""
    path = bench_manifest_path(xtest_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "pinned":
        _write_manifest(path, _identity("v0.38.1", "v0.38.1", "release"))
    elif kind == "malformed":
        path.write_text("{not json")
    elif kind == "directory":
        path.mkdir()


MANIFEST_STATES = ["absent", "pinned", "malformed", "directory"]


@pytest.fixture
def run_env(tmp_path: Path, monkeypatch):
    """Invoke the real `env` command against a stub platform under tmp_path."""
    from typer.testing import CliRunner

    (tmp_path / "opentdf-dev.yaml").write_text("services:\n  kas:\n    root_key: k\n")
    settings = Settings(xtest_root=tmp_path, platform_dir=tmp_path)
    # Bypass platform discovery and the version probe, which depend on the host.
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "get_platform_service", lambda _s: _StoppedPlatform())
    # Nor whatever the developer's own shell has exported.
    for name in (*cli.BENCH_VARS, cli.BENCH_EXPORTS_VAR):
        monkeypatch.delenv(name, raising=False)

    def _run(*args: str):
        result = CliRunner().invoke(cli.app, ["env", *args])
        assert result.exit_code == 0, result.output
        return result

    return _run


class TestEnvCommand:
    """What `eval $(otdf-local env)` and `env --format json | jq` actually see."""

    @pytest.mark.parametrize("state", MANIFEST_STATES)
    def test_shell_output_is_only_exports(self, state, tmp_path: Path, run_env):
        _prepare(state, tmp_path)
        result = run_env()
        for line in result.stdout.splitlines():
            assert re.fullmatch(
                r"export [A-Z][A-Z0-9_]*='.*';|unset [A-Z][A-Z0-9_]*;", line
            ), line

    @pytest.mark.parametrize("state", MANIFEST_STATES)
    def test_json_output_parses(self, state, tmp_path: Path, run_env):
        _prepare(state, tmp_path)
        result = run_env("--format", "json")
        assert json.loads(result.stdout)["PLATFORMURL"] == "http://localhost:8080"

    def test_unreadable_manifest_is_reported_on_stderr(self, tmp_path: Path, run_env):
        _prepare("malformed", tmp_path)
        result = run_env()
        assert "OTDFCTL_HEADS" not in result.stdout
        assert "Could not read OTDFCTL_HEADS" in result.stderr

    @pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
    @pytest.mark.parametrize("state", MANIFEST_STATES)
    def test_eval_exports_everything(self, state, tmp_path: Path, run_env):
        _prepare(state, tmp_path)
        platform_url, heads = _eval(run_env().stdout, "PLATFORMURL", "OTDFCTL_HEADS")
        assert platform_url == "http://localhost:8080"
        assert heads == ('["v0.38.1"]' if state == "pinned" else "<unset>")

    def test_xt_tmp_dir_defaults_to_xtest_tmp(
        self, tmp_path: Path, run_env, monkeypatch
    ):
        monkeypatch.delenv("XT_TMP_DIR", raising=False)
        exported = json.loads(run_env("--format", "json").stdout)
        assert exported["XT_TMP_DIR"] == str((tmp_path / "tmp").resolve())

    def test_xt_tmp_dir_already_set_is_kept(self, run_env, monkeypatch):
        # How a multi-GiB run is pointed at a large volume.
        monkeypatch.setenv("XT_TMP_DIR", "/mnt/big")
        exported = json.loads(run_env("--format", "json").stdout)
        assert exported["XT_TMP_DIR"] == "/mnt/big"

    @pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
    def test_rerun_unsets_what_the_last_run_exported(
        self, tmp_path: Path, run_env, monkeypatch
    ):
        _prepare("pinned", tmp_path)
        first = run_env().stdout
        bench_manifest_path(tmp_path).unlink()
        # The shell as the first eval left it.
        for name in (*cli.BENCH_VARS, cli.BENCH_EXPORTS_VAR):
            monkeypatch.setenv(name, _eval(first, name)[0])

        second = run_env().stdout

        # And the exports after the unsets still happen.
        assert _eval(second, *cli.BENCH_VARS, "PLATFORMURL") == [
            "<unset>",
            "<unset>",
            "http://localhost:8080",
        ]

    @pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
    def test_rerun_keeps_values_set_by_hand(self, run_env, monkeypatch):
        monkeypatch.setenv("BENCH_INSTALLATION_MANIFEST", "/elsewhere/m.json")
        monkeypatch.setenv("OTDFCTL_HEADS", '["v0.38.1"]')

        stdout = run_env().stdout

        assert "unset" not in stdout
        assert _eval(stdout, *cli.BENCH_VARS) == ["/elsewhere/m.json", '["v0.38.1"]']


def _eval(stdout: str, *names: str) -> list[str]:
    """The named variables after bash evals `stdout`, `<unset>` for unset ones.

    Unquoted, as documented, so word splitting and globbing both apply. The
    shell inherits the test's environment, as a user's shell would. A failing
    statement fails the call: `unset` skips arguments it cannot unset, so the
    variables asked about can look right while the rest went unexported.
    """
    printed = " ".join(f'"${{{name}-<unset>}}"' for name in names)
    shell = subprocess.run(
        ["bash", "-c", f'eval $1 || exit; printf "%s\\n" {printed}', "_", stdout],
        capture_output=True,
        text=True,
        check=True,
    )
    return shell.stdout.splitlines()
