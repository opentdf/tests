"""Tests for the benchmark environment `otdf-local env` exports.

The contract under test is cross-package: `otdf-sdk-mgr` writes the manifest,
`otdf-local` turns it into environment variables, and `xtest/conftest.py`
consumes them. Nothing in the type system connects those three, so the shape is
asserted here explicitly -- in particular that `OTDFCTL_HEADS` survives the
`json.loads` in `conftest.load_otdfctl`, which is the failure mode that hides:
an unparseable value falls back to an unpinned CLI, with a message pytest's
capture hides, and the run still reports success.
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

#: The manifest otdf-sdk-mgr's tests hold its writer and reader to. Every
#: manifest here is derived from it, so they have the shape that is written
#: rather than the shape this file remembers.
GOLDEN_MANIFEST = (
    Path(__file__).parents[2]
    / "otdf-sdk-mgr"
    / "tests"
    / "data"
    / "benchmark.installed.golden.json"
)
GOLDEN = json.loads(GOLDEN_MANIFEST.read_text())
PINNED_SHA = GOLDEN["otdfctl"]["commit_sha"]


def _write_manifest(
    path: Path, otdfctl: dict[str, object] | None, **rest: object
) -> Path:
    path.write_text(json.dumps({**GOLDEN, "otdfctl": otdfctl, **rest}))
    return path


def _identity(alias: str, tag: str, method: str) -> dict[str, object]:
    return {
        **GOLDEN["otdfctl"],
        "requested_alias": alias,
        "installed_tag": tag,
        "installed_path": f"/xtest/sdk/go/dist/{tag}",
        "installation_method": method,
    }


def _install(manifest_path: Path, tag: str, version: str | None = None) -> Path:
    """Lay down the go dist/ directory otdf-sdk-mgr would have installed `tag` to."""
    dist_dir = manifest_path.parent / "go" / "dist" / tag
    dist_dir.mkdir(parents=True)
    (dist_dir / "otdfctl.sh").touch()
    if version is not None:
        (dist_dir / ".version").write_text(version)
    return dist_dir


def _pinned(path: Path, **rest: object) -> Path:
    """A manifest whose otdfctl pin is installed, as `install benchmark` leaves it."""
    _install(path, "v0.38.1")
    return _write_manifest(path, _identity("v0.38.1", "v0.38.1", "release"), **rest)


def _refusal(path: Path, capsys: pytest.CaptureFixture[str]) -> str:
    """What `bench_manifest_env(path)` said on stderr when it exported no pin.

    Whatever the reason, it still points at the manifest, so the failure is
    diagnosable and the manifest's own reader decides what it means; and it
    says nothing on stdout, which is eval'd.
    """
    env = bench_manifest_env(path)
    assert "OTDFCTL_HEADS" not in env
    assert "BENCH_INSTALLATION_MANIFEST" in env
    out, err = capsys.readouterr()
    assert out == ""
    return err


class TestBenchManifestPath:
    def test_matches_the_sdk_manager_default(self, tmp_path: Path, monkeypatch):
        # Kept in step with otdf_sdk_mgr.bench_prepare.default_manifest_path,
        # which is get_sdk_dir() / "benchmark.installed.json" where get_sdk_dir
        # is <xtest>/sdk.
        monkeypatch.delenv("OTDF_SDK_DIR", raising=False)
        assert (
            bench_manifest_path(tmp_path)
            == tmp_path / "sdk" / "benchmark.installed.json"
        )

    def test_follows_the_sdk_dir_override(self, tmp_path: Path, monkeypatch):
        # As get_sdk_dir does; otherwise env looks where nothing was written.
        monkeypatch.setenv("OTDF_SDK_DIR", str(tmp_path / "elsewhere"))
        assert (
            bench_manifest_path(tmp_path)
            == tmp_path / "elsewhere" / "benchmark.installed.json"
        )


class TestBenchManifestEnv:
    def test_the_sdk_managers_golden_manifest_exports_its_pin(self, tmp_path: Path):
        # Verbatim, so a renamed or moved field in what otdf-sdk-mgr writes
        # fails here rather than silently dropping the pin.
        path = bench_manifest_path(tmp_path)
        path.parent.mkdir()
        shutil.copy(GOLDEN_MANIFEST, path)
        tag = GOLDEN["otdfctl"]["installed_tag"]
        _install(path, tag, f"github.com/opentdf/platform/otdfctl@{tag}\n")

        env = bench_manifest_env(path)

        assert env["OTDFCTL_HEADS"] == json.dumps([tag])

    def test_no_manifest_exports_nothing(self, tmp_path: Path):
        assert bench_manifest_env(tmp_path / "absent.json") == {}

    def test_manifest_pointer_is_absolute(self, tmp_path: Path):
        path = _write_manifest(tmp_path / "m.json", None)
        env = bench_manifest_env(path)
        assert Path(env["BENCH_INSTALLATION_MANIFEST"]).is_absolute()

    def test_otdfctl_heads_is_json_conftest_can_parse(self, tmp_path: Path):
        path = tmp_path / "m.json"
        _install(path, "refs--pull--123--head", f"ref=pr:123\nsha={PINNED_SHA}\n")
        _write_manifest(path, _identity("pr:123", "refs--pull--123--head", "source"))
        env = bench_manifest_env(path)
        # The exact parse conftest.load_otdfctl performs.
        assert json.loads(env["OTDFCTL_HEADS"]) == ["refs--pull--123--head"]

    def test_released_pin_is_exported_too(self, tmp_path: Path):
        # A release pin that is not exported silently reinstates the
        # dist/main fallback for a run that explicitly asked for a pin. A go
        # release's .version records no commit, so there is nothing to verify.
        path = tmp_path / "m.json"
        _install(path, "v0.24.0", "github.com/opentdf/otdfctl@v0.24.0\n")
        _write_manifest(path, _identity("v0.24.0", "v0.24.0", "release"))
        env = bench_manifest_env(path)
        assert json.loads(env["OTDFCTL_HEADS"]) == ["v0.24.0"]

    def test_exported_pin_is_announced_on_stderr(self, tmp_path: Path, capsys):
        # It applies to every later run in the shell, not only benchmarks.
        bench_manifest_env(_pinned(tmp_path / "m.json"))
        out, err = capsys.readouterr()
        assert out == ""
        assert "pins otdfctl to v0.38.1" in err

    def test_measured_arms_never_supply_otdfctl(self, tmp_path: Path, capsys):
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
        # Falling back is allowed, but not silently.
        assert "no otdfctl pin" in _refusal(path, capsys)

    @pytest.mark.parametrize("status", ["failed", "partial", "neutral"])
    def test_unsuccessful_preparation_exports_no_pin(
        self, status, tmp_path: Path, capsys
    ):
        # install benchmark installs otdfctl last, so its own manifests never
        # pair a pin with these; a hand-edited or foreign one might.
        path = _pinned(
            tmp_path / "m.json", status=status, status_message="arm 2 failed"
        )
        assert "arm 2 failed" in _refusal(path, capsys)

    def test_uninstalled_pin_is_not_exported(self, tmp_path: Path, capsys):
        # conftest would otherwise fail at import on the missing otdfctl.sh.
        path = _write_manifest(
            tmp_path / "m.json", _identity("v0.38.1", "v0.38.1", "release")
        )
        assert "no longer installed" in _refusal(path, capsys)

    def test_rebuilt_pin_is_not_exported(self, tmp_path: Path, capsys):
        # `install tip go` rebuilt dist/main after the benchmark pinned it, and
        # make deleted the .version that recorded the pinned commit.
        path = tmp_path / "m.json"
        _install(path, "main")
        _write_manifest(path, _identity("main", "main", "source"))
        assert "rebuilt" in _refusal(path, capsys)

    @pytest.mark.parametrize("tag", ["", True, 123, ["main"]])
    def test_pin_without_a_string_tag_exports_nothing(
        self, tag, tmp_path: Path, capsys
    ):
        # An empty tag would build the path sdk/go/dist//otdfctl.sh, and a
        # non-string one sdk/go/dist/True/otdfctl.sh.
        pin = {**_identity("main", "main", "source"), "installed_tag": tag}
        path = _write_manifest(tmp_path / "m.json", pin)
        assert "installed_tag" in _refusal(path, capsys)

    @pytest.mark.parametrize(
        "content", ["{not json", "[1, 2]", "null", '{"otdfctl": "v0.38.1"}']
    )
    def test_malformed_manifest_warns_without_raising(
        self, content, tmp_path: Path, capsys
    ):
        path = tmp_path / "m.json"
        path.write_text(content)
        assert "Not exporting OTDFCTL_HEADS" in _refusal(path, capsys)

    def test_markup_in_the_manifest_is_printed_not_parsed(self, tmp_path: Path, capsys):
        # Rich raises on an unmatched closing tag, and a raise empties stdout.
        path = _pinned(tmp_path / "m.json", status="failed", status_message="see [/x]")
        assert "see [/x]" in _refusal(path, capsys)


class _StoppedPlatform:
    def is_running(self) -> bool:
        return False


def _prepare(kind: str, xtest_root: Path) -> None:
    """Leave the manifest `env` will find in the state named by `kind`."""
    path = bench_manifest_path(xtest_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "pinned":
        _pinned(path)
    elif kind == "malformed":
        path.write_text("{not json")
    elif kind == "directory":
        path.mkdir()


MANIFEST_STATES = ["absent", "pinned", "malformed", "directory"]

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


@pytest.fixture
def run_env(tmp_path: Path, monkeypatch):
    """Invoke the real `env` command against a stub platform under tmp_path."""
    from typer.testing import CliRunner

    (tmp_path / "opentdf-dev.yaml").write_text("services:\n  kas:\n    root_key: k\n")
    settings = Settings(xtest_root=tmp_path, platform_dir=tmp_path)
    monkeypatch.delenv("OTDF_SDK_DIR", raising=False)
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
        assert "Not exporting OTDFCTL_HEADS" in result.stderr

    @needs_bash
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

    @needs_bash
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

    @needs_bash
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
