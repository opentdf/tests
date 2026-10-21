"""Tests for `otdf-sdk-mgr install benchmark`: exit codes and error reporting."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from otdf_sdk_mgr.cli_install import benchmark
from otdf_sdk_mgr.manifest import InstallationManifest, PreparationStatus


def _run(tmp_path: Path, **overrides) -> None:
    args = {
        "sdk": "go",
        "refs": ["v0.29.0", "main"],
        "platform": None,
        "otdfctl": None,
        "manifest": str(tmp_path / "m.json"),
    }
    args.update(overrides)
    benchmark(**args)


@pytest.mark.parametrize("status", [PreparationStatus.SUCCESS, PreparationStatus.NEUTRAL])
def test_success_and_neutral_exit_zero(tmp_path, status):
    """NEUTRAL is not an error: every alias named one commit, nothing to compare."""
    with patch(
        "otdf_sdk_mgr.cli_install.prepare_benchmark",
        return_value=InstallationManifest(status=status),
    ):
        _run(tmp_path)


def test_success_with_a_warning_exits_zero_and_shows_it(tmp_path, capsys):
    with patch(
        "otdf_sdk_mgr.cli_install.prepare_benchmark",
        return_value=InstallationManifest(
            status=PreparationStatus.SUCCESS, status_message="v0.38.0 = main"
        ),
    ):
        _run(tmp_path)

    assert "v0.38.0 = main" in capsys.readouterr().err


@pytest.mark.parametrize("status", [PreparationStatus.PARTIAL, PreparationStatus.FAILED])
def test_partial_and_failed_exit_one(tmp_path, status, capsys):
    """A caller reads the exit code to decide whether to measure the installs."""
    with (
        patch(
            "otdf_sdk_mgr.cli_install.prepare_benchmark",
            return_value=InstallationManifest(status=status, status_message="boom"),
        ),
        pytest.raises(typer.Exit) as exc,
    ):
        _run(tmp_path)

    assert exc.value.exit_code == 1
    assert "boom" in capsys.readouterr().err


def test_arguments_reach_prepare_benchmark(tmp_path):
    with patch(
        "otdf_sdk_mgr.cli_install.prepare_benchmark",
        return_value=InstallationManifest(status=PreparationStatus.SUCCESS),
    ) as mock_prepare:
        _run(tmp_path, sdk="java", platform="main", otdfctl="v0.24.0")

    mock_prepare.assert_called_once_with(
        sdk="java",
        requested_aliases=["v0.29.0", "main"],
        platform_ref="main",
        otdfctl_ref="v0.24.0",
        manifest_path=tmp_path / "m.json",
    )


def test_unlocatable_sdk_dir_is_an_error_not_a_traceback(tmp_path, capsys):
    """`get_sdk_dir` raises RuntimeError outside a checkout; that is setup, not a bug."""
    with (
        patch(
            "otdf_sdk_mgr.cli_install.default_manifest_path",
            side_effect=RuntimeError("Could not locate xtest/sdk"),
        ),
        patch("otdf_sdk_mgr.cli_install.prepare_benchmark") as mock_prepare,
        pytest.raises(typer.Exit) as exc,
    ):
        _run(tmp_path, manifest=None)

    assert exc.value.exit_code == 1
    assert "Could not locate xtest/sdk" in capsys.readouterr().err
    mock_prepare.assert_not_called()


def test_unwritable_manifest_path_is_an_error_not_a_traceback(tmp_path, capsys):
    with (
        patch(
            "otdf_sdk_mgr.cli_install.prepare_benchmark",
            side_effect=PermissionError(13, "Permission denied"),
        ),
        pytest.raises(typer.Exit) as exc,
    ):
        _run(tmp_path)

    assert exc.value.exit_code == 1
    assert "Permission denied" in capsys.readouterr().err


def test_failed_install_exits_one_and_leaves_a_manifest(tmp_path):
    """Through the real prepare_benchmark, with resolution and installation faked."""
    from otdf_sdk_mgr.bench_prepare import BenchPrepareError
    from otdf_sdk_mgr.manifest import ResolvedArtifact

    arm = ResolvedArtifact(
        requested_alias="main",
        repository="https://github.com/opentdf/platform.git",
        commit_sha="def456",
        tag="main",
        is_head=True,
        is_release=False,
    )
    with (
        patch("otdf_sdk_mgr.bench_prepare.resolve_ordered", return_value=([arm], None)),
        patch(
            "otdf_sdk_mgr.bench_prepare.install_artifact",
            side_effect=BenchPrepareError("make failed"),
        ),
        pytest.raises(typer.Exit) as exc,
    ):
        _run(tmp_path, refs=["main"])

    assert exc.value.exit_code == 1
    on_disk = InstallationManifest.read(tmp_path / "m.json")
    assert on_disk.status == PreparationStatus.FAILED
    assert "make failed" in on_disk.status_message


def test_an_error_after_the_manifest_is_written_still_names_it(tmp_path, capsys):
    """The manifest records what the run did before it failed; point at it."""
    from otdf_sdk_mgr.manifest import ResolvedArtifact

    arm = ResolvedArtifact(
        requested_alias="main",
        repository="https://github.com/opentdf/platform.git",
        commit_sha="def456",
        tag="main",
        is_head=True,
        is_release=False,
    )
    with (
        patch("otdf_sdk_mgr.bench_prepare.resolve_ordered", return_value=([arm], None)),
        patch(
            "otdf_sdk_mgr.bench_prepare.install_artifact",
            side_effect=PermissionError(13, "Permission denied", "dist/main"),
        ),
        pytest.raises(typer.Exit) as exc,
    ):
        _run(tmp_path, refs=["main"])

    assert exc.value.exit_code == 1
    err = capsys.readouterr().err
    assert "Permission denied" in err
    assert f"Manifest: {tmp_path / 'm.json'}" in err
    assert InstallationManifest.read(tmp_path / "m.json").status == PreparationStatus.FAILED
