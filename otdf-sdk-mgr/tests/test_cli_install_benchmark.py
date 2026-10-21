"""Tests for `otdf-sdk-mgr install benchmark`: exit codes and error reporting."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner, Result

from otdf_sdk_mgr.cli_install import install_app
from otdf_sdk_mgr.manifest import (
    ArtifactIdentity,
    InstallationManifest,
    PreparationStatus,
    ResolvedArtifact,
)


def sha_of(label: str) -> str:
    """A full commit SHA standing for `label`: distinct labels, distinct commits."""
    return hashlib.sha1(label.encode()).hexdigest()


def _run(tmp_path: Path, *args: str) -> Result:
    """Invoke `install benchmark` through Typer, as the shell would.

    Through the registered command, not the function, so a renamed option or a
    lost registration fails here too.
    """
    argv = ["benchmark", *(args or ("go", "v0.29.0", "main"))]
    return CliRunner().invoke(install_app, [*argv, "--manifest", str(tmp_path / "m.json")])


def _assert_exit_one(result: Result) -> None:
    """Exit 1 by typer.Exit: CliRunner reports an uncaught exception as 1 too."""
    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, SystemExit), repr(result.exception)


def _main_arm() -> ResolvedArtifact:
    return ResolvedArtifact(
        requested_alias="main",
        repository="https://github.com/opentdf/platform.git",
        commit_sha=sha_of("def456"),
        tag="main",
        is_head=True,
        is_release=False,
    )


@pytest.mark.parametrize("status", [PreparationStatus.SUCCESS, PreparationStatus.NEUTRAL])
def test_success_and_neutral_exit_zero(tmp_path, status):
    """NEUTRAL is not an error: every alias named one commit, nothing to compare."""
    with patch(
        "otdf_sdk_mgr.cli_install.prepare_benchmark",
        return_value=InstallationManifest(status=status),
    ):
        result = _run(tmp_path)

    assert result.exit_code == 0, result.output


def test_success_with_a_warning_exits_zero_and_shows_it(tmp_path):
    with patch(
        "otdf_sdk_mgr.cli_install.prepare_benchmark",
        return_value=InstallationManifest(
            status=PreparationStatus.SUCCESS, status_message="v0.38.0 = main"
        ),
    ):
        result = _run(tmp_path)

    assert result.exit_code == 0, result.output
    assert "v0.38.0 = main" in result.stderr


@pytest.mark.parametrize("status", [PreparationStatus.PARTIAL, PreparationStatus.FAILED])
def test_partial_and_failed_exit_one(tmp_path, status):
    """A caller reads the exit code to decide whether to measure the installs."""
    with patch(
        "otdf_sdk_mgr.cli_install.prepare_benchmark",
        return_value=InstallationManifest(status=status, status_message="boom"),
    ):
        result = _run(tmp_path)

    _assert_exit_one(result)
    assert "boom" in result.stderr


def test_arguments_reach_prepare_benchmark(tmp_path):
    with patch(
        "otdf_sdk_mgr.cli_install.prepare_benchmark",
        return_value=InstallationManifest(status=PreparationStatus.SUCCESS),
    ) as mock_prepare:
        result = _run(
            tmp_path, "java", "v0.29.0", "main", "--platform", "main", "--otdfctl", "v0.24.0"
        )

    assert result.exit_code == 0, result.output
    mock_prepare.assert_called_once_with(
        sdk="java",
        requested_aliases=["v0.29.0", "main"],
        platform_ref="main",
        otdfctl_ref="v0.24.0",
        manifest_path=tmp_path / "m.json",
    )


def test_unlocatable_sdk_dir_is_an_error_not_a_traceback(tmp_path):
    """`get_sdk_dir` raises RuntimeError outside a checkout; that is setup, not a bug.

    Checked even with `--manifest`, since every install lands under xtest/sdk.
    """
    with (
        patch(
            "otdf_sdk_mgr.cli_install.default_manifest_path",
            side_effect=RuntimeError("Could not locate xtest/sdk"),
        ),
        patch("otdf_sdk_mgr.cli_install.prepare_benchmark") as mock_prepare,
    ):
        result = _run(tmp_path)

    _assert_exit_one(result)
    assert "Could not locate xtest/sdk" in result.stderr
    mock_prepare.assert_not_called()


def test_unwritable_manifest_path_is_an_error_that_names_no_manifest(tmp_path):
    """Nothing this run wrote is on disk, so there is no manifest to point at."""
    (tmp_path / "file").write_text("")

    with patch("otdf_sdk_mgr.bench_prepare.resolve_ordered") as mock_resolve:
        result = CliRunner().invoke(
            install_app,
            ["benchmark", "go", "main", "--manifest", str(tmp_path / "file" / "m.json")],
        )

    _assert_exit_one(result)
    assert "cannot write the manifest" in result.stderr
    assert "Manifest:" not in result.output
    mock_resolve.assert_not_called()


def test_failed_install_exits_one_and_leaves_a_manifest(tmp_path):
    """Through the real prepare_benchmark, with resolution and installation faked."""
    with (
        patch("otdf_sdk_mgr.bench_prepare.resolve_ordered", return_value=([_main_arm()], None)),
        patch(
            "otdf_sdk_mgr.bench_prepare.install_artifact",
            side_effect=PermissionError(13, "Permission denied", "dist/main"),
        ),
    ):
        result = _run(tmp_path, "go", "main")

    _assert_exit_one(result)
    assert "Permission denied" in result.stderr
    assert f"Manifest: {tmp_path / 'm.json'}" in result.stdout
    on_disk = InstallationManifest.read(tmp_path / "m.json")
    assert on_disk.status == PreparationStatus.FAILED
    assert "Permission denied" in on_disk.status_message


def test_a_failed_final_write_still_names_the_manifest(tmp_path):
    """The file the first write left records this run as unfinished; point at it."""
    real_write = InstallationManifest.write
    writes: list[PreparationStatus] = []

    def write(manifest, path):
        writes.append(manifest.status)
        if len(writes) > 1:
            raise OSError(28, "No space left on device")
        real_write(manifest, path)

    with (
        patch("otdf_sdk_mgr.bench_prepare.resolve_ordered", return_value=([_main_arm()], None)),
        patch(
            "otdf_sdk_mgr.bench_prepare.install_artifact",
            return_value=ArtifactIdentity(
                requested_alias="main",
                repository="https://github.com/opentdf/platform.git",
                commit_sha=sha_of("def456"),
                installed_tag="main",
                installed_path=str(tmp_path / "dist" / "main"),
                installation_method="source",
            ),
        ),
        patch.object(InstallationManifest, "write", write),
    ):
        result = _run(tmp_path, "go", "main")

    _assert_exit_one(result)
    assert "No space left on device" in result.stderr
    assert f"Manifest: {tmp_path / 'm.json'}" in result.stderr
    assert "did not finish" in InstallationManifest.read(tmp_path / "m.json").status_message


def test_an_abbreviated_sha_fails_before_anything_installs(tmp_path):
    """An abbreviation would hide that two arms are one commit; ask for the full SHA."""
    full = sha_of("main")

    def resolve(sdk, ref, infix=None):
        if ref == "main":
            return {"sdk": sdk, "alias": ref, "sha": full, "tag": "main", "head": True}
        return {"sdk": sdk, "alias": ref, "sha": ref, "tag": ref}

    with (
        patch("otdf_sdk_mgr.bench_prepare.resolve", side_effect=resolve),
        patch("otdf_sdk_mgr.bench_prepare.install_artifact") as mock_install,
    ):
        result = _run(tmp_path, "go", full[:7], "main")

    _assert_exit_one(result)
    assert f"give the full commit SHA for {full[:7]}" in result.stderr
    mock_install.assert_not_called()
    on_disk = InstallationManifest.read(tmp_path / "m.json")
    assert on_disk.status == PreparationStatus.FAILED
    assert on_disk.sdk_arms == []
