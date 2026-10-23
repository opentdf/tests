"""Tests for the java and js release installers — network and subprocesses are mocked."""

import subprocess
import urllib.error
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import git.exc
import pytest

from otdf_sdk_mgr import installers
from otdf_sdk_mgr.installers import (
    InstallError,
    install_java_release,
    install_js_release,
    latest_stable_version,
)


def http_error(url: str, code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "error", MagicMock(), None)


def http_404(url: str) -> urllib.error.HTTPError:
    return http_error(url, 404)


@pytest.fixture
def sdk_dir(tmp_path: Path) -> Iterator[Path]:
    for sdk in ("java", "js"):
        (tmp_path / sdk).mkdir()
        (tmp_path / sdk / "cli.sh").write_text("#!/bin/sh\n")
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


def fake_js_build(cmd: list[str], cwd: Path | None = None) -> int:
    """Stand-in for check_call: lay down what clone + npm pack would produce."""
    if cmd[:2] == ["git", "clone"]:
        (Path(cmd[-1]) / "cli").mkdir(parents=True)
    elif cmd[:2] == ["npm", "pack"]:
        dest = Path(cmd[cmd.index("--pack-destination") + 1])
        (dest / "opentdf-ctl-0.22.0.tgz").write_text("tgz")
    return 0


def npm_has(*published: str):
    """`_on_npm` stand-in: True only for the given `package@version` specs."""
    return lambda package, version: f"{package}@{version}" in published


class TestInstallJsRelease:
    @pytest.mark.parametrize("version", ["sdk-v0.20.0", "sdk/v0.20.0", "v0.20.0", "0.20.0"])
    def test_cli_on_npm_installs_it(self, sdk_dir: Path, version: str):
        dist = sdk_dir / "js" / "dist" / "v0.20.0"
        with (
            patch.object(installers, "_on_npm", side_effect=npm_has("@opentdf/ctl@0.20.0")),
            patch("otdf_sdk_mgr.installers.subprocess.check_call") as cc,
        ):
            install_js_release(version, dist)
        cc.assert_called_once_with(["npm", "install", "@opentdf/ctl@0.20.0"], cwd=dist)
        assert (dist / "cli.sh").exists()

    def test_cli_missing_builds_against_npm_sdk(self, sdk_dir: Path):
        dist = sdk_dir / "js" / "dist" / "v0.22.0"
        with (
            patch.object(installers, "_on_npm", side_effect=npm_has("@opentdf/sdk@0.22.0")),
            patch.object(installers, "_js_release_tag", return_value="sdk-v0.22.0"),
            patch("otdf_sdk_mgr.installers.subprocess.check_call", side_effect=fake_js_build) as cc,
        ):
            install_js_release("sdk-v0.22.0", dist)

        cmds = [c.args[0] for c in cc.call_args_list]
        assert "--branch=sdk-v0.22.0" in cmds[0]
        # The CLI resolves the published sdk, not ../lib's tarball, so the lib
        # never has to be built.
        assert ["npm", "install", "--save-exact", "@opentdf/sdk@0.22.0"] in cmds
        assert cmds[-1] == ["npm", "install", "./opentdf-ctl-0.22.0.tgz"]
        assert cc.call_args_list[-1].kwargs["cwd"] == dist
        # Kept beside package.json, whose file: dependency points at it.
        assert (dist / "opentdf-ctl-0.22.0.tgz").read_text() == "tgz"
        assert (dist / "cli.sh").exists()

    def test_nothing_on_npm_raises_for_source_fallback(self, sdk_dir: Path):
        dist = sdk_dir / "js" / "dist" / "v0.23.0"
        with (
            patch.object(installers, "_on_npm", return_value=False),
            patch("otdf_sdk_mgr.installers.subprocess.check_call") as cc,
            pytest.raises(InstallError, match="Neither @opentdf/ctl nor @opentdf/sdk"),
        ):
            install_js_release("v0.23.0", dist)
        cc.assert_not_called()
        assert not dist.exists()

    def test_npm_install_failure_leaves_no_partial_dist(self, sdk_dir: Path):
        dist = sdk_dir / "js" / "dist" / "v0.20.0"
        with (
            patch.object(installers, "_on_npm", return_value=True),
            patch(
                "otdf_sdk_mgr.installers.subprocess.check_call",
                side_effect=subprocess.CalledProcessError(1, ["npm"]),
            ),
            pytest.raises(InstallError, match="from npm failed"),
        ):
            install_js_release("v0.20.0", dist)
        # A leftover dist with only cli.sh would be skipped as installed next run.
        assert not dist.exists()

    def test_interrupted_npm_install_leaves_no_partial_dist(self, sdk_dir: Path):
        dist = sdk_dir / "js" / "dist" / "v0.20.0"
        with (
            patch.object(installers, "_on_npm", return_value=True),
            patch(
                "otdf_sdk_mgr.installers.subprocess.check_call",
                side_effect=KeyboardInterrupt(),
            ),
            pytest.raises(KeyboardInterrupt),
        ):
            install_js_release("v0.20.0", dist)
        assert not dist.exists()

    def test_interrupted_install_of_a_built_cli_leaves_no_partial_dist(self, sdk_dir: Path):
        dist = sdk_dir / "js" / "dist" / "v0.22.0"

        def install_interrupted(cmd: list[str], cwd: Path | None = None) -> int:
            if cwd == dist:
                raise KeyboardInterrupt
            return fake_js_build(cmd, cwd)

        with (
            patch.object(installers, "_on_npm", side_effect=npm_has("@opentdf/sdk@0.22.0")),
            patch.object(installers, "_js_release_tag", return_value="sdk-v0.22.0"),
            patch("otdf_sdk_mgr.installers.subprocess.check_call", side_effect=install_interrupted),
            pytest.raises(KeyboardInterrupt),
        ):
            install_js_release("v0.22.0", dist)
        assert not dist.exists()

    def test_build_failure_raises_without_dist(self, sdk_dir: Path):
        dist = sdk_dir / "js" / "dist" / "v0.22.0"

        def ci_fails(cmd: list[str], cwd: Path | None = None) -> int:
            if cmd[:2] == ["npm", "ci"]:
                raise subprocess.CalledProcessError(1, cmd)
            return fake_js_build(cmd, cwd)

        with (
            patch.object(installers, "_on_npm", side_effect=npm_has("@opentdf/sdk@0.22.0")),
            patch.object(installers, "_js_release_tag", return_value="sdk-v0.22.0"),
            patch("otdf_sdk_mgr.installers.subprocess.check_call", side_effect=ci_fails),
            pytest.raises(InstallError, match="Running npm ci for the 0.22.0 CLI failed"),
        ):
            install_js_release("v0.22.0", dist)
        assert not dist.exists()


class TestJsReleaseTag:
    def ls_remote(self, *tags: str):
        mock_git = MagicMock()
        mock_git.ls_remote.return_value = "\n".join(f"{'a' * 40}\trefs/tags/{t}" for t in tags)
        return patch("otdf_sdk_mgr.installers.Git", return_value=mock_git)

    def test_dash_form(self):
        with self.ls_remote("sdk-v0.22.0"):
            assert installers._js_release_tag("0.22.0") == "sdk-v0.22.0"

    def test_slash_form_up_to_0_4_0(self):
        with self.ls_remote("sdk/v0.4.0"):
            assert installers._js_release_tag("0.4.0") == "sdk/v0.4.0"

    def test_missing_raises(self):
        with self.ls_remote(), pytest.raises(InstallError, match="No web-sdk tag for sdk 0.99.0"):
            installers._js_release_tag("0.99.0")

    def test_git_failure_raises_install_error(self):
        mock_git = MagicMock()
        mock_git.ls_remote.side_effect = git.exc.GitCommandError("ls-remote", 128)
        with (
            patch("otdf_sdk_mgr.installers.Git", return_value=mock_git),
            pytest.raises(InstallError, match="Could not list web-sdk tags"),
        ):
            installers._js_release_tag("0.22.0")


class TestOnNpm:
    def test_found(self):
        with patch.object(installers, "fetch_json", return_value={"version": "0.22.0"}) as fj:
            assert installers._on_npm("@opentdf/sdk", "0.22.0") is True
        fj.assert_called_once_with("https://registry.npmjs.org/@opentdf/sdk/0.22.0")

    def test_missing(self):
        with patch.object(
            installers, "fetch_json", side_effect=http_404("https://registry.npmjs.org/x")
        ):
            assert installers._on_npm("@opentdf/ctl", "0.22.0") is False

    def test_server_error_raises(self):
        with (
            patch.object(
                installers,
                "fetch_json",
                side_effect=http_error("https://registry.npmjs.org/x", 503),
            ),
            pytest.raises(InstallError, match="Could not check npm"),
        ):
            installers._on_npm("@opentdf/ctl", "0.22.0")

    def test_unreachable_raises(self):
        with (
            patch.object(installers, "fetch_json", side_effect=urllib.error.URLError("no route")),
            pytest.raises(InstallError, match="Could not reach npm"),
        ):
            installers._on_npm("@opentdf/ctl", "0.22.0")


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

    def test_js_is_newest_release_tag_not_newest_npm_cli(self):
        resolved = {"sdk": "js", "alias": "latest", "sha": "a" * 40, "tag": "v0.22.0"}
        with patch.object(installers, "resolve", return_value=resolved) as res:
            assert latest_stable_version("js") == "v0.22.0"
        res.assert_called_once_with("js", "latest", "sdk")

    def test_js_resolve_error_raises(self):
        err = {"sdk": "js", "alias": "latest", "err": "no tags"}
        with (
            patch.object(installers, "resolve", return_value=err),
            pytest.raises(InstallError, match="no tags"),
        ):
            latest_stable_version("js")


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


class TestCmdTip:
    @pytest.mark.parametrize("sdk", ["go", "java", "js"])
    @pytest.mark.parametrize(
        "ref",
        ["main", "pr:123", "feature/x", "sdk/v1.2.3", "otdfctl/v0.24.0", "a" * 40],
    )
    def test_builds_into_the_directory_install_benchmark_predicts(
        self, tmp_path: Path, sdk: str, ref: str
    ):
        """`install benchmark` looks for the build at `dist_slug_for`; make writes `dist/$VERSIONS`."""
        from otdf_sdk_mgr.manifest import ResolvedArtifact, dist_slug_for

        envs: list[dict[str, str]] = []
        with (
            patch.object(installers, "get_sdk_dirs", return_value={sdk: tmp_path}),
            patch.object(installers, "checkout_sdk_branch"),
            patch("otdf_sdk_mgr.checkout.checkout_go_from_platform", return_value=tmp_path),
            patch.object(
                installers.subprocess,
                "check_call",
                side_effect=lambda cmd, cwd, env: envs.append(env),
            ),
        ):
            installers.cmd_tip([sdk], ref=ref)

        predicted = dist_slug_for(
            ResolvedArtifact(
                requested_alias=ref,
                repository="",
                commit_sha=None,
                tag="",
                is_head=True,
                is_release=False,
            )
        )
        assert envs[0]["VERSIONS"] == predicted
