"""Tests for the java release installer — network and subprocesses are mocked."""

import subprocess
import urllib.error
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from otdf_sdk_mgr import installers
from otdf_sdk_mgr.installers import InstallError, install_java_release, latest_stable_version


def http_error(url: str, code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "error", MagicMock(), None)


def http_404(url: str) -> urllib.error.HTTPError:
    return http_error(url, 404)


@pytest.fixture
def sdk_dir(tmp_path: Path) -> Iterator[Path]:
    java_dir = tmp_path / "java"
    java_dir.mkdir()
    (java_dir / "cli.sh").write_text("#!/bin/sh\n")
    with patch("otdf_sdk_mgr.installers.get_sdk_dir", return_value=tmp_path):
        yield tmp_path


def fake_build(cmd: list[str]) -> int:
    """Stand-in for check_call: lay down what clone + mvn would produce."""
    if cmd[0] == "git":
        Path(cmd[-1]).mkdir(parents=True)
    elif cmd[0] == "mvn":
        target = Path(cmd[cmd.index("--file") + 1]).parent / "cmdline" / "target"
        target.mkdir(parents=True)
        (target / "cmdline.jar").write_text("jar")
    return 0


class TestInstallJavaRelease:
    def test_no_github_asset_builds_cmdline_only_against_maven_central(self, sdk_dir: Path):
        dist = sdk_dir / "java" / "dist" / "v0.19.1"
        with (
            patch.object(
                installers,
                "_download_java_github_release",
                side_effect=InstallError("cmdline.jar not found"),
            ),
            patch.object(installers, "_java_sdk_on_maven_central", return_value=True),
            patch("otdf_sdk_mgr.installers.subprocess.check_call", side_effect=fake_build) as cc,
        ):
            install_java_release("0.19.1", dist)

        clone, mvn = (c.args[0] for c in cc.call_args_list)
        assert "--branch=v0.19.1" in clone
        # Only the parent pom and the CLI: the sdk module (and its buf codegen)
        # must not be in the reactor.
        assert mvn[mvn.index("--projects") + 1] == ".,cmdline"
        # Isolated from ~/.m2/repository, where a head build may have
        # installed a same-versioned sdk.
        assert f"-Dmaven.repo.local={installers.JAVA_RELEASE_MAVEN_REPO}" in mvn
        assert (dist / "cmdline.jar").read_text() == "jar"
        assert (dist / "cli.sh").exists()

    def test_not_on_maven_central_raises_for_source_fallback(self, sdk_dir: Path):
        dist = sdk_dir / "java" / "dist" / "v0.17.0"
        with (
            patch.object(
                installers,
                "_download_java_github_release",
                side_effect=InstallError("cmdline.jar not found"),
            ),
            patch.object(installers, "_java_sdk_on_maven_central", return_value=False),
            patch("otdf_sdk_mgr.installers.subprocess.check_call") as cc,
            pytest.raises(InstallError, match="not published to Maven Central"),
        ):
            install_java_release("v0.17.0", dist)
        cc.assert_not_called()
        assert not dist.exists()

    def test_mvn_failure_raises_with_both_causes(self, sdk_dir: Path):
        dist = sdk_dir / "java" / "dist" / "v0.9.0"

        def mvn_fails(cmd: list[str]) -> int:
            if cmd[0] == "mvn":
                raise subprocess.CalledProcessError(1, cmd)
            return fake_build(cmd)

        with (
            patch.object(
                installers,
                "_download_java_github_release",
                side_effect=InstallError("cmdline.jar not found"),
            ),
            patch.object(installers, "_java_sdk_on_maven_central", return_value=True),
            patch("otdf_sdk_mgr.installers.subprocess.check_call", side_effect=mvn_fails),
            pytest.raises(InstallError) as exc,
        ):
            install_java_release("v0.9.0", dist)
        assert "cmdline.jar not found" in str(exc.value)
        assert "Running mvn for the v0.9.0 CLI failed" in str(exc.value)
        assert not dist.exists()

    def test_copy_failure_leaves_no_partial_dist(self, sdk_dir: Path):
        dist = sdk_dir / "java" / "dist" / "v0.19.1"
        real_copy = installers.shutil.copy

        def copy_fails_on_jar(src: Path, dst: Path) -> object:
            if Path(dst).name == "cmdline.jar":
                raise OSError("disk full")
            return real_copy(src, dst)

        with (
            patch.object(
                installers,
                "_download_java_github_release",
                side_effect=InstallError("cmdline.jar not found"),
            ),
            patch.object(installers, "_java_sdk_on_maven_central", return_value=True),
            patch("otdf_sdk_mgr.installers.subprocess.check_call", side_effect=fake_build),
            patch("otdf_sdk_mgr.installers.shutil.copy", side_effect=copy_fails_on_jar),
            pytest.raises(InstallError, match="could not install it"),
        ):
            install_java_release("v0.19.1", dist)
        # A leftover dist with only cli.sh would be skipped as installed next run.
        assert not dist.exists()

    def test_github_asset_skips_maven_build(self, sdk_dir: Path):
        dist = sdk_dir / "java" / "dist" / "v0.19.1"
        with (
            patch.object(installers, "_download_java_github_release") as download,
            patch("otdf_sdk_mgr.installers.subprocess.check_call") as cc,
        ):
            install_java_release("v0.19.1", dist)
        download.assert_called_once_with("v0.19.1", dist)
        cc.assert_not_called()


class TestDownloadJavaGithubRelease:
    def test_rate_limit_raises_install_error(self, sdk_dir: Path):
        # Not a bare HTTPError: install_java_release only falls through to the
        # Maven Central build on InstallError.
        with (
            patch(
                "otdf_sdk_mgr.installers.urllib.request.urlopen",
                side_effect=http_error("https://github.com/x", 403),
            ),
            pytest.raises(InstallError, match="Could not check GitHub"),
        ):
            installers._download_java_github_release("v0.19.1", sdk_dir / "dist")


class TestLatestStableVersion:
    def test_java_ignores_has_cli(self):
        releases = [
            {"version": "v0.1.0", "stable": True, "has_cli": True},
            {"version": "v0.2.0", "stable": True, "has_cli": False},
            {"version": "v0.3.0-rc1", "stable": False, "has_cli": False},
        ]
        with patch.object(installers, "list_java_github_releases", return_value=releases):
            assert latest_stable_version("java") == "v0.2.0"

    def test_java_none_stable(self):
        with patch.object(installers, "list_java_github_releases", return_value=[]):
            assert latest_stable_version("java") is None


class TestJavaSdkOnMavenCentral:
    def test_found(self):
        with patch("otdf_sdk_mgr.installers.urllib.request.urlopen", MagicMock()) as urlopen:
            assert installers._java_sdk_on_maven_central("v0.19.1") is True
        url = urlopen.call_args.args[0].full_url
        assert url.endswith("/io/opentdf/platform/sdk/0.19.1/sdk-0.19.1.pom")

    def test_missing(self):
        with patch(
            "otdf_sdk_mgr.installers.urllib.request.urlopen",
            side_effect=http_404("https://repo1.maven.org/x"),
        ):
            assert installers._java_sdk_on_maven_central("v0.17.0") is False

    def test_unreachable_raises(self):
        with (
            patch(
                "otdf_sdk_mgr.installers.urllib.request.urlopen",
                side_effect=urllib.error.URLError("no route"),
            ),
            pytest.raises(InstallError, match="Could not reach Maven Central"),
        ):
            installers._java_sdk_on_maven_central("v0.19.1")

    def test_server_error_raises(self):
        with (
            patch(
                "otdf_sdk_mgr.installers.urllib.request.urlopen",
                side_effect=http_error("https://repo1.maven.org/x", 503),
            ),
            pytest.raises(InstallError, match="Could not check Maven Central"),
        ):
            installers._java_sdk_on_maven_central("v0.19.1")
