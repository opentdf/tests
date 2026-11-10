"""Tests for the benchmark environment `otdf-local env` exports.

The contract is cross-package, with no shared import: `otdf-sdk-mgr` writes the
manifest, `otdf-local` turns it into environment variables, and
`xtest/conftest.py` consumes them. A wrong or missing `OTDFCTL_HEADS` fails
nothing: conftest falls back to an unpinned CLI, its message lost to pytest's
capture, and the run still passes.
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

    Asserts that it still exported the manifest path, and printed nothing on
    stdout, which is eval'd.
    """
    env = bench_manifest_env(path)
    assert "OTDFCTL_HEADS" not in env
    assert "BENCH_INSTALLATION_MANIFEST" in env
    out, err = capsys.readouterr()
    assert out == ""
    return err


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

    def test_otdfctl_heads_is_json_conftest_can_parse(self, tmp_path: Path):
        path = tmp_path / "m.json"
        _install(path, "refs--pull--123--head", f"ref=pr:123\nsha={PINNED_SHA}\n")
        _write_manifest(path, _identity("pr:123", "refs--pull--123--head", "source"))
        env = bench_manifest_env(path)
        # The exact parse conftest.load_otdfctl performs.
        assert json.loads(env["OTDFCTL_HEADS"]) == ["refs--pull--123--head"]

    def test_measured_arms_never_supply_otdfctl(self, tmp_path: Path, capsys):
        # The pin comes only from `otdfctl`, never inferred from the arms.
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

    def test_unsuccessful_preparation_exports_no_pin(self, tmp_path: Path, capsys):
        # install benchmark installs otdfctl last, so its own manifests never
        # pair a pin with a failure; a hand-edited or foreign one might.
        path = _pinned(
            tmp_path / "m.json", status="partial", status_message="arm 2 failed"
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

    def test_pin_without_a_string_tag_exports_nothing(self, tmp_path: Path, capsys):
        # Building the dist path from a non-string tag would raise TypeError.
        pin = {**_identity("main", "main", "source"), "installed_tag": 123}
        path = _write_manifest(tmp_path / "m.json", pin)
        assert "installed_tag" in _refusal(path, capsys)

    @pytest.mark.parametrize("content", ["{not json", "[1, 2]"])
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


needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


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
    """What a shell's eval and `env --format json | jq` actually see."""

    @needs_bash
    @pytest.mark.parametrize("state", ["absent", "pinned", "malformed"])
    def test_shell_output_evals_to_the_exports(self, state, tmp_path: Path, run_env):
        _prepare(state, tmp_path)
        stdout = run_env().stdout
        for line in stdout.splitlines():
            assert re.fullmatch(
                r"export [A-Z][A-Z0-9_]*='.*';|unset [A-Z][A-Z0-9_]*;", line
            ), line
        platform_url, heads = _eval(stdout, "PLATFORMURL", "OTDFCTL_HEADS")
        assert platform_url == "http://localhost:8080"
        assert heads == ('["v0.38.1"]' if state == "pinned" else "<unset>")

    def test_json_output_parses_despite_warnings(self, tmp_path: Path, run_env):
        _prepare("malformed", tmp_path)
        result = run_env("--format", "json")
        assert json.loads(result.stdout)["PLATFORMURL"] == "http://localhost:8080"

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

    Unquoted, the worst case, so word splitting and globbing both apply. The
    shell inherits the test's environment, as a user's shell would. `|| exit`
    catches lines run together into one `unset`, which fails on the
    `KEY=value` words it cannot unset.
    """
    printed = " ".join(f'"${{{name}-<unset>}}"' for name in names)
    shell = subprocess.run(
        ["bash", "-c", f'eval $1 || exit; printf "%s\\n" {printed}', "_", stdout],
        capture_output=True,
        text=True,
        check=True,
    )
    return shell.stdout.splitlines()
