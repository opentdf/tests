"""The benchmark command's argument and exit-code contract."""

from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from otdf_sdk_mgr import cli_install
from otdf_sdk_mgr.manifest import InstallationManifest, PreparationStatus


def run(tmp_path, *args):
    return CliRunner().invoke(
        cli_install.install_app,
        ["benchmark", *args, "--manifest", str(tmp_path / "m.json")],
    )


def test_passes_refs_and_pins_to_preparation(monkeypatch, tmp_path):
    prepare = Mock(return_value=InstallationManifest(status=PreparationStatus.SUCCESS))
    monkeypatch.setattr(cli_install, "prepare_benchmark", prepare)

    result = run(tmp_path, "java", "v1.0.0", "main", "--platform", "main", "--otdfctl", "v0.24.0")

    assert result.exit_code == 0, result.output
    prepare.assert_called_once_with(
        sdk="java",
        requested_aliases=["v1.0.0", "main"],
        platform_ref="main",
        otdfctl_ref="v0.24.0",
        manifest_path=tmp_path / "m.json",
    )


@pytest.mark.parametrize(
    ("status", "exit_code"),
    [
        (PreparationStatus.SUCCESS, 0),
        (PreparationStatus.NEUTRAL, 0),
        (PreparationStatus.PARTIAL, 1),
        (PreparationStatus.FAILED, 1),
    ],
)
def test_exit_code_tracks_manifest_status(monkeypatch, tmp_path, status, exit_code):
    monkeypatch.setattr(
        cli_install,
        "prepare_benchmark",
        lambda **kwargs: InstallationManifest(status=status, status_message="detail"),
    )

    result = run(tmp_path, "go", "main")

    assert result.exit_code == exit_code, result.output
    assert str(tmp_path / "m.json") in result.output
    assert "detail" in result.output


def test_unwritable_manifest_exits_without_pointing_at_an_old_file(monkeypatch, tmp_path):
    def fail(**kwargs):
        raise cli_install.BenchPrepareError("cannot write the manifest")

    monkeypatch.setattr(cli_install, "prepare_benchmark", fail)

    result = run(tmp_path, "go", "main")

    assert result.exit_code == 1
    assert "cannot write the manifest" in result.output
    assert "Manifest:" not in result.output
