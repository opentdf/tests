"""Tests for bench_prepare.py - ordered resolution and installation."""

import hashlib
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from otdf_sdk_mgr import platform_installer
from otdf_sdk_mgr.bench_prepare import (
    BenchPrepareError,
    install_artifact,
    prepare_benchmark,
    resolve_ordered,
)
from otdf_sdk_mgr.manifest import (
    ArtifactIdentity,
    InstallationManifest,
    PreparationStatus,
    ResolvedArtifact,
)
from otdf_sdk_mgr.refs import dist_slug, expand_pr_shorthand


def sha_of(label: str) -> str:
    """A full commit SHA standing for `label`: distinct labels, distinct commits."""
    return hashlib.sha1(label.encode()).hexdigest()


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _identity(tag: str, commit_sha: str) -> ArtifactIdentity:
    """A plausible install result, for tests that only care that one happened."""
    return ArtifactIdentity(
        requested_alias=tag,
        repository="https://github.com/opentdf/platform.git",
        commit_sha=commit_sha,
        installed_tag=tag,
        installed_path=f"/sdk/go/dist/{tag}",
        installation_method="release",
    )


class TestResolveOrdered:
    @patch("otdf_sdk_mgr.bench_prepare.resolve")
    @patch("otdf_sdk_mgr.bench_prepare.expand_pr_shorthand")
    def test_resolve_two_refs(self, mock_expand, mock_resolve):
        # Setup mocks
        mock_expand.side_effect = lambda x: x  # no-op for non-pr refs

        mock_resolve.side_effect = [
            {
                "sdk": "go",
                "alias": "v0.29.0",
                "sha": sha_of("abc123"),
                "tag": "v0.29.0",
                "release": "otdfctl/v0.29.0",
            },
            {
                "sdk": "go",
                "alias": "main",
                "sha": sha_of("def456"),
                "tag": "main",
                "head": True,
            },
        ]

        resolved, error = resolve_ordered("go", ["v0.29.0", "main"])

        assert error is None
        assert len(resolved) == 2
        assert resolved[0].requested_alias == "v0.29.0"
        assert resolved[0].commit_sha == sha_of("abc123")
        assert resolved[0].is_release is True
        assert resolved[1].requested_alias == "main"
        assert resolved[1].commit_sha == sha_of("def456")
        assert resolved[1].is_head is True

    @patch("otdf_sdk_mgr.bench_prepare.resolve")
    def test_resolve_expands_pr_shorthand(self, mock_resolve):
        mock_resolve.return_value = {
            "sdk": "go",
            "alias": "pr:123",
            "sha": sha_of("abc123"),
            "tag": "pull-123",
            "head": True,
            "pr": "123",
        }

        resolved, error = resolve_ordered("go", ["pr:123"])

        assert error is None
        assert len(resolved) == 1
        assert resolved[0].requested_alias == "pr:123"
        assert mock_resolve.call_args.args[1] == "refs/pull/123/head"

    @pytest.mark.parametrize(
        ("sdk", "infix"),
        [("go", None), ("java", None), ("js", "sdk")],
    )
    @patch("otdf_sdk_mgr.bench_prepare.resolve")
    def test_resolve_uses_each_repos_tag_namespace(self, mock_resolve, sdk, infix):
        """java-sdk tags are bare `vX.Y.Z`; web-sdk's carry the `sdk` infix.

        go's `otdfctl/` namespace is `resolve`'s business, so go passes none.

        Passing `sdk` for java filters every java tag out, so each java
        release, `latest` and `lts` arm fails with "Tag not found".
        """
        mock_resolve.return_value = {
            "sdk": sdk,
            "alias": "v0.9.0",
            "sha": sha_of("abc123"),
            "tag": "v0.9.0",
            "release": "v0.9.0",
        }

        resolve_ordered(sdk, ["v0.9.0"])

        mock_resolve.assert_called_once_with(sdk, "v0.9.0", infix=infix)

    @patch("otdf_sdk_mgr.bench_prepare.resolve")
    @patch("otdf_sdk_mgr.bench_prepare.expand_pr_shorthand")
    def test_resolve_same_commit_preserves_aliases(self, mock_expand, mock_resolve):
        # Both aliases resolve to the same commit
        mock_expand.side_effect = lambda x: x
        mock_resolve.side_effect = [
            {
                "sdk": "go",
                "alias": "v0.29.0",
                "sha": sha_of("same_commit"),
                "tag": "v0.29.0",
                "release": "otdfctl/v0.29.0",
            },
            {
                "sdk": "go",
                "alias": "main",
                "sha": sha_of("same_commit"),
                "tag": "main",
                "head": True,
            },
        ]

        resolved, error = resolve_ordered("go", ["v0.29.0", "main"])

        assert error is None
        assert len(resolved) == 2  # Both preserved
        assert resolved[0].commit_sha == resolved[1].commit_sha

    @patch("otdf_sdk_mgr.bench_prepare.resolve")
    def test_npm_only_release_has_no_commit_rather_than_an_empty_one(self, mock_resolve):
        """Every npm-only release resolves with sha ""; as a commit it is one they all share."""
        mock_resolve.return_value = {
            "sdk": "js",
            "alias": "v0.4.0",
            "sha": "",
            "tag": "0.4.0",
            "release": "0.4.0",
        }

        resolved, error = resolve_ordered("js", ["v0.4.0"])

        assert error is None
        assert resolved[0].commit_sha is None

    @patch("otdf_sdk_mgr.bench_prepare.resolve")
    def test_bare_sha_builds_from_source(self, mock_resolve):
        """A SHA no ref points at resolves as neither head nor release."""
        full = sha_of("bare")
        mock_resolve.return_value = {"sdk": "go", "alias": full[:7], "sha": full, "tag": full}

        resolved, _ = resolve_ordered("go", [full])

        assert resolved[0].installation_method == "source"

    @patch("otdf_sdk_mgr.bench_prepare.resolve")
    def test_abbreviated_sha_is_an_error_not_a_commit(self, mock_resolve):
        """A SHA no ref points at comes back as typed.

        Abbreviated, it would not compare equal to the full SHA another arm
        resolved to, so one commit would build twice and report SUCCESS.
        """
        mock_resolve.return_value = {
            "sdk": "go",
            "alias": "abc1234",
            "sha": "abc1234",
            "tag": "abc1234",
        }

        resolved, error = resolve_ordered("go", ["abc1234", "main"])

        assert resolved == []
        assert error is not None
        assert "give the full commit SHA for abc1234" in error
        mock_resolve.assert_called_once()

    def test_no_refs_is_an_error(self):
        """Not a SUCCESS that installed nothing."""
        resolved, error = resolve_ordered("go", [])

        assert resolved == []
        assert error == "No refs requested"

    @patch("otdf_sdk_mgr.bench_prepare.resolve")
    @patch("otdf_sdk_mgr.bench_prepare.expand_pr_shorthand")
    def test_resolve_failure_returns_error(self, mock_expand, mock_resolve):
        mock_expand.side_effect = lambda x: x
        mock_resolve.return_value = {
            "sdk": "go",
            "alias": "nonexistent",
            "err": "ref not found",
        }

        resolved, error = resolve_ordered("go", ["nonexistent"])

        assert error is not None
        assert "Failed to resolve" in error
        assert "nonexistent" in error
        assert len(resolved) == 0

    def test_resolve_unknown_sdk(self):
        resolved, error = resolve_ordered("python", ["main"])

        assert error is not None
        assert "Unknown SDK" in error
        assert len(resolved) == 0

    @patch("otdf_sdk_mgr.bench_prepare.resolve")
    def test_platform_is_not_an_sdk(self, mock_resolve):
        """ "platform" resolves, but is no SDK: there is no sdk/platform/dist.

        Accepting it ended in a KeyError traceback with no manifest, or, for
        `platform main main`, a NEUTRAL exit 0.
        """
        resolved, error = resolve_ordered("platform", ["main"])

        assert error is not None
        assert "Unknown SDK" in error
        assert resolved == []
        mock_resolve.assert_not_called()


class TestPrepareBenchmark:
    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_neutral_preparation_same_commit(self, mock_resolve, mock_install, tmp_path):
        # Both resolve to same commit
        mock_resolve.return_value = (
            [
                ResolvedArtifact(
                    requested_alias="v0.29.0",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha=sha_of("same_commit"),
                    tag="v0.29.0",
                    is_head=False,
                    is_release=True,
                ),
                ResolvedArtifact(
                    requested_alias="main",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha=sha_of("same_commit"),
                    tag="main",
                    is_head=True,
                    is_release=False,
                ),
            ],
            None,
        )

        manifest = prepare_benchmark("go", ["v0.29.0", "main"], manifest_path=tmp_path / "m.json")

        assert manifest.status == PreparationStatus.NEUTRAL
        assert "same commit" in manifest.status_message.lower()
        # Nothing is installed, but the collapse is recorded: a reader has to be
        # able to see *which* commit both arms landed on, not merely that they did.
        mock_install.assert_not_called()
        assert [arm.commit_sha for arm in manifest.sdk_arms] == [sha_of("same_commit")] * 2
        assert [arm.requested_alias for arm in manifest.sdk_arms] == ["v0.29.0", "main"]
        # None unconditionally, not "None because the directory happens to be
        # absent". A leftover `dist/main` from an earlier run is common, and
        # naming it would claim a provenance this preparation never checked.
        assert all(arm.installed_path is None for arm in manifest.sdk_arms)
        assert manifest.metadata == {"sdk": "go"}
        assert InstallationManifest.read(tmp_path / "m.json") == manifest

    @patch("otdf_sdk_mgr.bench_prepare.install_platform_source")
    @patch("otdf_sdk_mgr.bench_prepare.install_platform_release")
    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_neutral_installs_no_platform_or_otdfctl_either(
        self, mock_resolve, mock_install, mock_release, mock_source, tmp_path
    ):
        """NEUTRAL means nothing was installed, pins included."""
        arms = [
            ResolvedArtifact(
                requested_alias=alias,
                repository="https://github.com/opentdf/platform.git",
                commit_sha=sha_of("same_commit"),
                tag=alias,
                is_head=True,
                is_release=False,
            )
            for alias in ("main", "pr:1")
        ]
        pin = ResolvedArtifact(
            requested_alias="v0.24.0",
            repository="https://github.com/opentdf/platform.git",
            commit_sha=sha_of("pin"),
            tag="v0.24.0",
            is_head=False,
            is_release=True,
        )
        mock_resolve.side_effect = [(arms, None), ([pin], None)]

        manifest = prepare_benchmark(
            "go",
            ["main", "pr:1"],
            platform_ref="main",
            otdfctl_ref="v0.24.0",
            manifest_path=tmp_path / "m.json",
        )

        assert manifest.status == PreparationStatus.NEUTRAL
        mock_install.assert_not_called()
        mock_release.assert_not_called()
        mock_source.assert_not_called()
        assert manifest.platform is None
        assert manifest.otdfctl is None

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_resolution_failure(self, mock_resolve, mock_install, tmp_path):
        mock_resolve.return_value = ([], "Failed to resolve go@bogus: ref not found")

        manifest = prepare_benchmark("go", ["bogus"], manifest_path=tmp_path / "m.json")

        assert manifest.status == PreparationStatus.FAILED
        assert "Failed to resolve" in manifest.status_message
        assert InstallationManifest.read(tmp_path / "m.json") == manifest
        mock_install.assert_not_called()

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_namespaced_and_plain_branches_collide_on_the_dist_path(
        self, mock_resolve, mock_install, tmp_path
    ):
        """js `sdk/feature` and `feature` are distinct refs and one directory.

        cmd_tip strips the `sdk--` prefix, so both build into `dist/feature`.
        Bucketing on the raw ref sees two different strings and waves this
        through; the second build replaces the first and the run measures one
        commit against itself.
        """
        mock_resolve.return_value = (
            [
                ResolvedArtifact(
                    requested_alias=alias,
                    repository="https://github.com/opentdf/web-sdk.git",
                    commit_sha=sha,
                    tag=alias.replace("/", "--"),
                    is_head=True,
                    is_release=False,
                )
                for alias, sha in [("sdk/feature", "a" * 40), ("feature", "b" * 40)]
            ],
            None,
        )

        manifest = prepare_benchmark(
            "js", ["sdk/feature", "feature"], manifest_path=tmp_path / "m.json"
        )

        assert manifest.status == PreparationStatus.FAILED
        assert "Colliding installed paths" in manifest.status_message
        # The commits are named because they are what makes it a collision:
        # one directory cannot hold both.
        assert "feature: sdk/feature at aaaaaaaa; feature at bbbbbbbb" in manifest.status_message
        assert InstallationManifest.read(tmp_path / "m.json") == manifest
        mock_install.assert_not_called()

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_one_commit_in_one_directory_is_neutral_not_a_collision(
        self, mock_resolve, mock_install, tmp_path
    ):
        """Two refs at one commit share a directory harmlessly: one build.

        The run is NEUTRAL, and says which commit, rather than FAILED with a
        collision that would hide why the benchmark is meaningless.
        """
        mock_resolve.return_value = (
            [
                ResolvedArtifact(
                    requested_alias=alias,
                    repository="https://github.com/opentdf/web-sdk.git",
                    commit_sha=sha_of("onecommit"),
                    tag=alias.replace("/", "--"),
                    is_head=True,
                    is_release=False,
                )
                for alias in ("sdk/feature", "feature")
            ],
            None,
        )

        manifest = prepare_benchmark(
            "js", ["sdk/feature", "feature"], manifest_path=tmp_path / "m.json"
        )

        assert manifest.status == PreparationStatus.NEUTRAL
        assert sha_of("onecommit")[:8] in manifest.status_message
        mock_install.assert_not_called()

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_provisioning_pin_may_name_an_arms_own_commit(
        self, mock_resolve, mock_install, tmp_path
    ):
        """`--otdfctl v0.24.0` while measuring v0.24.0 is not a collision.

        The pin and the arm are one commit, so they are one build; sharing the
        directory changes nothing. Rejecting this would outlaw the ordinary
        request to provision with a build already in the run.
        """
        arm = ResolvedArtifact(
            requested_alias="v0.24.0",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="a" * 40,
            tag="v0.24.0",
            is_head=False,
            is_release=True,
        )
        main = ResolvedArtifact(
            requested_alias="main",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="b" * 40,
            tag="main",
            is_head=True,
            is_release=False,
        )
        mock_resolve.side_effect = [([arm, main], None), ([arm], None)]
        mock_install.return_value = _identity("v0.24.0", "a" * 40)

        manifest = prepare_benchmark(
            "go",
            ["v0.24.0", "main"],
            otdfctl_ref="v0.24.0",
            manifest_path=tmp_path / "m.json",
        )

        assert manifest.status == PreparationStatus.SUCCESS
        assert manifest.otdfctl is not None

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_provisioning_pin_colliding_at_another_commit_fails_before_builds(
        self, mock_resolve, mock_install, tmp_path
    ):
        """A pin landing on an arm's directory at a different commit is fatal.

        `otdfctl/feature` and `feature` both build into go's `dist/feature`,
        so installing the pin would rebuild a directory the run is measuring
        -- and nothing afterwards could tell which build is in it.
        """

        def branch(alias: str, sha: str) -> ResolvedArtifact:
            return ResolvedArtifact(
                requested_alias=alias,
                repository="https://github.com/opentdf/platform.git",
                commit_sha=sha,
                tag=alias.replace("/", "--"),
                is_head=True,
                is_release=False,
            )

        arms = [branch("feature", "a" * 40), branch("main", "b" * 40)]
        mock_resolve.side_effect = [(arms, None), ([branch("otdfctl/feature", "c" * 40)], None)]

        manifest = prepare_benchmark(
            "go",
            ["feature", "main"],
            otdfctl_ref="otdfctl/feature",
            manifest_path=tmp_path / "m.json",
        )

        assert manifest.status == PreparationStatus.FAILED
        assert "Colliding installed paths" in manifest.status_message
        mock_install.assert_not_called()

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_unresolvable_provisioning_pin_fails_before_builds(
        self, mock_resolve, mock_install, tmp_path
    ):
        # Resolving the pin last meant a typo in it was reported only after
        # every arm had been compiled.
        arm = ResolvedArtifact(
            requested_alias="main",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="b" * 40,
            tag="main",
            is_head=True,
            is_release=False,
        )
        mock_resolve.side_effect = [([arm], None), ([], "no such ref: v9.9.9")]

        manifest = prepare_benchmark(
            "go", ["main"], otdfctl_ref="v9.9.9", manifest_path=tmp_path / "m.json"
        )

        assert manifest.status == PreparationStatus.FAILED
        assert "otdfctl" in manifest.status_message
        assert "v9.9.9" in manifest.status_message
        mock_install.assert_not_called()

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_go_provisioning_pin_cannot_collide_with_java_arms(
        self, mock_resolve, mock_install, tmp_path
    ):
        """otdfctl is always the Go CLI and lives in the go dist/ tree.

        A java arm tagged `v0.24.0` and a Go pin tagged `v0.24.0` slug the
        same but occupy different trees, so folding the pin into the check
        unconditionally would reject a valid run.
        """
        arm = ResolvedArtifact(
            requested_alias="v0.24.0",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="a" * 40,
            tag="v0.24.0",
            is_head=False,
            is_release=True,
        )
        main = ResolvedArtifact(
            requested_alias="main",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="b" * 40,
            tag="main",
            is_head=True,
            is_release=False,
        )
        pin = ResolvedArtifact(
            requested_alias="v0.24.0",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="c" * 40,
            tag="v0.24.0",
            is_head=False,
            is_release=True,
        )
        mock_resolve.side_effect = [([arm, main], None), ([pin], None)]
        mock_install.return_value = _identity("v0.24.0", "c" * 40)

        manifest = prepare_benchmark(
            "java",
            ["v0.24.0", "main"],
            otdfctl_ref="v0.24.0",
            manifest_path=tmp_path / "m.json",
        )

        assert manifest.status == PreparationStatus.SUCCESS
        # Resolved and installed against "go", not against the measured SDK.
        assert mock_resolve.call_args_list[1].args[0] == "go"
        assert mock_install.call_args_list[-1].args[0] == "go"

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_successful_preparation(self, mock_resolve, mock_install, tmp_path):
        from otdf_sdk_mgr.manifest import ArtifactIdentity

        mock_resolve.return_value = (
            [
                ResolvedArtifact(
                    requested_alias="v0.29.0",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha=sha_of("abc123"),
                    tag="v0.29.0",
                    is_head=False,
                    is_release=True,
                ),
                ResolvedArtifact(
                    requested_alias="main",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha=sha_of("def456"),
                    tag="main",
                    is_head=True,
                    is_release=False,
                ),
            ],
            None,
        )

        # Mock installations
        mock_install.side_effect = [
            ArtifactIdentity(
                requested_alias="v0.29.0",
                repository="https://github.com/opentdf/platform.git",
                commit_sha=sha_of("abc123"),
                installed_tag="v0.29.0",
                installed_path="/path/to/v0.29.0",
                installation_method="release",
            ),
            ArtifactIdentity(
                requested_alias="main",
                repository="https://github.com/opentdf/platform.git",
                commit_sha=sha_of("def456"),
                installed_tag="main",
                installed_path="/path/to/main",
                installation_method="source",
            ),
        ]

        manifest = prepare_benchmark("go", ["v0.29.0", "main"], manifest_path=tmp_path / "m.json")

        assert manifest.status == PreparationStatus.SUCCESS
        assert len(manifest.sdk_arms) == 2
        assert manifest.sdk_arms[0].requested_alias == "v0.29.0"
        assert manifest.sdk_arms[1].requested_alias == "main"
        assert mock_install.call_count == 2
        assert InstallationManifest.read(tmp_path / "m.json") == manifest

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_arms_that_repeat_a_build_succeed_with_a_warning(
        self, mock_resolve, mock_install, tmp_path
    ):
        """Not every arm is one build, so not NEUTRAL; but two of them are."""
        arms = [
            ResolvedArtifact(
                requested_alias=alias,
                repository="https://github.com/opentdf/platform.git",
                commit_sha=sha,
                tag=alias,
                is_head=alias != "v0.38.0",
                is_release=alias == "v0.38.0",
            )
            for alias, sha in [
                ("v0.38.0", sha_of("aaa")),
                ("main", sha_of("aaa")),
                ("pr:123", sha_of("bbb")),
            ]
        ]
        mock_resolve.return_value = (arms, None)
        mock_install.side_effect = lambda sdk, a: _identity(a.requested_alias, a.commit_sha)

        manifest = prepare_benchmark(
            "go", ["v0.38.0", "main", "pr:123"], manifest_path=tmp_path / "m.json"
        )

        assert manifest.status == PreparationStatus.SUCCESS
        assert "v0.38.0 = main" in manifest.status_message
        assert "pr:123" not in manifest.status_message

    @staticmethod
    def _npm_only(sdk, ref, infix=None):
        """`resolve` for a js release on npm whose tag is not in git: no sha."""
        version = "0.4.0" if ref == "latest" else ref.removeprefix("v")
        return {"sdk": sdk, "alias": ref, "release": f"sdk/{version}", "sha": "", "tag": version}

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve")
    def test_npm_only_releases_of_one_version_are_neutral(
        self, mock_resolve, mock_install, tmp_path
    ):
        """With no commit to compare, one release is one directory."""
        mock_resolve.side_effect = self._npm_only

        manifest = prepare_benchmark("js", ["latest", "v0.4.0"], manifest_path=tmp_path / "m.json")

        assert manifest.status == PreparationStatus.NEUTRAL
        assert "whose commit is unknown" in manifest.status_message
        assert [arm.commit_sha for arm in manifest.sdk_arms] == [None, None]
        mock_install.assert_not_called()
        assert InstallationManifest.read(tmp_path / "m.json") == manifest

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve")
    def test_npm_only_releases_of_two_versions_are_not_neutral(
        self, mock_resolve, mock_install, tmp_path
    ):
        """No commit is not one shared commit: two versions are two builds."""
        mock_resolve.side_effect = self._npm_only
        mock_install.side_effect = lambda sdk, a: _identity(a.requested_alias, a.commit_sha)

        manifest = prepare_benchmark("js", ["v0.4.0", "v0.5.0"], manifest_path=tmp_path / "m.json")

        assert manifest.status == PreparationStatus.SUCCESS
        assert manifest.status_message == ""
        assert mock_install.call_count == 2

    @pytest.mark.parametrize(
        ("error", "reported"),
        [
            (BenchPrepareError("Installation failed"), "Installation failed"),
            # A stale dist it cannot remove: a status, not an abort.
            (PermissionError(13, "Permission denied", "dist/v0.29.0"), "Permission denied"),
        ],
    )
    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_install_failure(self, mock_resolve, mock_install, tmp_path, error, reported):
        mock_resolve.return_value = (
            [
                ResolvedArtifact(
                    requested_alias="v0.29.0",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha=sha_of("abc123"),
                    tag="v0.29.0",
                    is_head=False,
                    is_release=True,
                ),
            ],
            None,
        )

        mock_install.side_effect = error

        manifest = prepare_benchmark("go", ["v0.29.0"], manifest_path=tmp_path / "m.json")

        # Nothing installed, so nothing partial: FAILED.
        assert manifest.status == PreparationStatus.FAILED
        assert reported in manifest.status_message
        assert "aborted" not in manifest.status_message
        assert InstallationManifest.read(tmp_path / "m.json") == manifest

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_failure_after_an_installed_arm_keeps_that_arm(
        self, mock_resolve, mock_install, tmp_path
    ):
        """PARTIAL lists what did install, so a reader knows what is on disk."""
        mock_resolve.return_value = (
            [
                ResolvedArtifact(
                    requested_alias="v0.29.0",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha=sha_of("abc123"),
                    tag="v0.29.0",
                    is_head=False,
                    is_release=True,
                ),
                ResolvedArtifact(
                    requested_alias="main",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha=sha_of("def456"),
                    tag="main",
                    is_head=True,
                    is_release=False,
                ),
            ],
            None,
        )
        first = _identity("v0.29.0", sha_of("abc123"))
        mock_install.side_effect = [first, BenchPrepareError("make failed")]

        manifest = prepare_benchmark("go", ["v0.29.0", "main"], manifest_path=tmp_path / "m.json")

        assert manifest.status == PreparationStatus.PARTIAL
        assert manifest.sdk_arms == [first]
        assert InstallationManifest.read(tmp_path / "m.json") == manifest

    @pytest.mark.parametrize(
        "error", [BenchPrepareError("go install failed"), PermissionError(13, "Permission denied")]
    )
    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_otdfctl_install_failure_is_partial(self, mock_resolve, mock_install, tmp_path, error):
        """`install_artifact`'s documented failures, a dist it cannot remove included."""
        arm = ResolvedArtifact(
            requested_alias="main",
            repository="https://github.com/opentdf/platform.git",
            commit_sha=sha_of("def456"),
            tag="main",
            is_head=True,
            is_release=False,
        )
        pin = ResolvedArtifact(
            requested_alias="v0.24.0",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="c" * 40,
            tag="v0.24.0",
            is_head=False,
            is_release=True,
        )
        mock_resolve.side_effect = [([arm], None), ([pin], None)]
        mock_install.side_effect = [
            _identity("main", sha_of("def456")),
            error,
        ]

        manifest = prepare_benchmark(
            "go", ["main"], otdfctl_ref="v0.24.0", manifest_path=tmp_path / "m.json"
        )

        assert manifest.status == PreparationStatus.PARTIAL
        assert "Failed to install otdfctl" in manifest.status_message
        assert manifest.otdfctl is None
        assert [arm.requested_alias for arm in manifest.sdk_arms] == ["main"]
        assert InstallationManifest.read(tmp_path / "m.json") == manifest


class TestManifestOnEveryPath:
    """The file at manifest_path always describes the run that just ended."""

    def _arms(self) -> list[ResolvedArtifact]:
        return [
            ResolvedArtifact(
                requested_alias="v0.29.0",
                repository="https://github.com/opentdf/platform.git",
                commit_sha=sha_of("abc123"),
                tag="v0.29.0",
                is_head=False,
                is_release=True,
            ),
            ResolvedArtifact(
                requested_alias="main",
                repository="https://github.com/opentdf/platform.git",
                commit_sha=sha_of("def456"),
                tag="main",
                is_head=True,
                is_release=False,
            ),
        ]

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_interrupted_install_replaces_the_previous_runs_manifest(
        self, mock_resolve, mock_install, tmp_path
    ):
        """Ctrl-C mid-build must not leave yesterday's SUCCESS on disk.

        A caller that reads `status` from the file would otherwise go on to
        measure a half-installed run.
        """
        path = tmp_path / "m.json"
        InstallationManifest(status=PreparationStatus.SUCCESS).write(path)
        mock_resolve.return_value = (self._arms(), None)
        mock_install.side_effect = [_identity("v0.29.0", sha_of("abc123")), KeyboardInterrupt()]

        with pytest.raises(KeyboardInterrupt):
            prepare_benchmark("go", ["v0.29.0", "main"], manifest_path=path)

        on_disk = InstallationManifest.read(path)
        assert on_disk.status == PreparationStatus.PARTIAL
        assert "KeyboardInterrupt" in on_disk.status_message
        assert [arm.requested_alias for arm in on_disk.sdk_arms] == ["v0.29.0"]

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_mid_build_the_file_already_says_did_not_finish(
        self, mock_resolve, mock_install, tmp_path
    ):
        """A run killed outright never reaches its final write.

        What is on disk while it builds has to be this run's FAILED, not
        yesterday's SUCCESS.
        """
        path = tmp_path / "m.json"
        InstallationManifest(status=PreparationStatus.SUCCESS).write(path)
        mock_resolve.return_value = (self._arms(), None)
        seen: list[InstallationManifest] = []

        def install(sdk, artifact):
            seen.append(InstallationManifest.read(path))
            return _identity(artifact.requested_alias, artifact.commit_sha)

        mock_install.side_effect = install

        prepare_benchmark("go", ["v0.29.0", "main"], manifest_path=path)

        assert seen[0].status == PreparationStatus.FAILED
        assert "did not finish" in seen[0].status_message

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_a_failed_abort_write_keeps_the_original_exception(
        self, mock_resolve, mock_install, tmp_path, capsys
    ):
        """A full disk must not turn Ctrl-C into an OSError, or hide why it stopped."""
        path = tmp_path / "m.json"
        mock_resolve.return_value = (self._arms(), None)
        mock_install.side_effect = KeyboardInterrupt()
        real_write = InstallationManifest.write
        writes: list[PreparationStatus] = []

        def write(manifest, p):
            writes.append(manifest.status)
            if len(writes) > 1:
                raise OSError(28, "No space left on device")
            real_write(manifest, p)

        with (
            patch.object(InstallationManifest, "write", write),
            pytest.raises(KeyboardInterrupt),
        ):
            prepare_benchmark("go", ["v0.29.0", "main"], manifest_path=path)

        assert "could not record the abort" in capsys.readouterr().err
        on_disk = InstallationManifest.read(path)
        assert "did not finish" in on_disk.status_message

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_unexpected_error_before_any_install_is_recorded_as_failed(
        self, mock_resolve, mock_install, tmp_path
    ):
        path = tmp_path / "m.json"
        mock_resolve.side_effect = KeyError("platform")

        with pytest.raises(KeyError):
            prepare_benchmark("go", ["main"], manifest_path=path)

        on_disk = InstallationManifest.read(path)
        assert on_disk.status == PreparationStatus.FAILED
        assert "KeyError" in on_disk.status_message
        mock_install.assert_not_called()

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_unwritable_manifest_path_fails_before_resolving(
        self, mock_resolve, mock_install, tmp_path
    ):
        """A typo'd --manifest should cost nothing, not every build first."""
        (tmp_path / "file").write_text("")

        with pytest.raises(BenchPrepareError, match="cannot write the manifest"):
            prepare_benchmark("go", ["main"], manifest_path=tmp_path / "file" / "m.json")

        mock_resolve.assert_not_called()
        mock_install.assert_not_called()

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_manifest_directory_is_created_before_any_build(
        self, mock_resolve, mock_install, tmp_path
    ):
        """A `--manifest` into a new directory once failed after every build."""
        path = tmp_path / "results" / "run1" / "m.json"
        mock_resolve.return_value = (self._arms(), None)

        def install(sdk, artifact):
            assert path.exists(), "manifest path untested until after the builds"
            return _identity(artifact.requested_alias, artifact.commit_sha)

        mock_install.side_effect = install

        manifest = prepare_benchmark("go", ["v0.29.0", "main"], manifest_path=path)

        assert manifest.status == PreparationStatus.SUCCESS
        assert InstallationManifest.read(path) == manifest


class TestPlatformPin:
    """`--platform` is recorded from what the platform installer left on disk."""

    def _platform_dist(self, tmp_path: Path, name: str, sha: str | None) -> Path:
        """A platform dist, with `.version` written by the real writer."""
        dist = tmp_path / "platform" / "dist" / name
        dist.mkdir(parents=True)
        if sha is not None:
            with patch.object(platform_installer, "_git_rev_parse", return_value=sha):
                platform_installer._record_version(dist, name, tmp_path / "worktree")
        return dist

    def _prepare(self, tmp_path: Path, platform_ref: str):
        arms = [
            ResolvedArtifact(
                requested_alias="v0.29.0",
                repository="https://github.com/opentdf/platform.git",
                commit_sha=sha_of("abc123"),
                tag="v0.29.0",
                is_head=False,
                is_release=True,
            ),
            ResolvedArtifact(
                requested_alias="main",
                repository="https://github.com/opentdf/platform.git",
                commit_sha=sha_of("def456"),
                tag="main",
                is_head=True,
                is_release=False,
            ),
        ]
        with (
            patch("otdf_sdk_mgr.bench_prepare.resolve_ordered", return_value=(arms, None)),
            patch(
                "otdf_sdk_mgr.bench_prepare.install_artifact",
                side_effect=lambda sdk, a: _identity(a.requested_alias, a.commit_sha),
            ),
        ):
            return prepare_benchmark(
                "go",
                ["v0.29.0", "main"],
                platform_ref=platform_ref,
                manifest_path=tmp_path / "m.json",
            )

    @patch("otdf_sdk_mgr.bench_prepare.install_platform_source")
    def test_pin_records_the_commit_and_directory_the_installer_chose(self, mock_source, tmp_path):
        """`installed_tag` is the dist directory, not the ref that was asked for."""
        mock_source.return_value = self._platform_dist(
            tmp_path, "refs--pull--42--head", sha="f00dcafe" * 5
        )

        manifest = self._prepare(tmp_path, "pr:42")

        assert manifest.status == PreparationStatus.SUCCESS
        mock_source.assert_called_once_with("refs/pull/42/head")
        assert manifest.platform is not None
        assert manifest.platform.commit_sha == "f00dcafe" * 5
        assert manifest.platform.installed_tag == "refs--pull--42--head"
        assert manifest.platform.requested_alias == "pr:42"

    @pytest.mark.parametrize("sha", [None, "abc1234"])
    @patch("otdf_sdk_mgr.bench_prepare.install_platform_release")
    def test_platform_without_a_recorded_commit_is_partial(self, mock_release, tmp_path, sha):
        """A pin with no full commit in it pins nothing a reader can check out."""
        mock_release.return_value = self._platform_dist(tmp_path, "v0.9.0", sha=sha)

        manifest = self._prepare(tmp_path, "v0.9.0")

        assert manifest.status == PreparationStatus.PARTIAL
        assert "without a recorded commit" in manifest.status_message
        assert manifest.platform is None
        # The arms installed before the platform failed are still on record.
        assert [arm.requested_alias for arm in manifest.sdk_arms] == ["v0.29.0", "main"]
        assert InstallationManifest.read(tmp_path / "m.json") == manifest

    @patch("otdf_sdk_mgr.bench_prepare.install_platform_source")
    def test_platform_install_error_is_partial(self, mock_source, tmp_path):
        mock_source.side_effect = platform_installer.PlatformInstallError("go build failed")

        manifest = self._prepare(tmp_path, "main")

        assert manifest.status == PreparationStatus.PARTIAL
        assert "Failed to install platform: go build failed" in manifest.status_message
        assert InstallationManifest.read(tmp_path / "m.json") == manifest


class TestInstallRelease:
    """Release arms go through `install_release`, into the directory slugged for them."""

    def _artifact(self) -> ResolvedArtifact:
        return ResolvedArtifact(
            requested_alias="v0.4.0",
            repository="https://github.com/opentdf/web-sdk.git",
            commit_sha=sha_of("abc123"),
            tag="0.4.0",
            is_head=False,
            is_release=True,
        )

    @patch("otdf_sdk_mgr.bench_prepare.install_release")
    @patch("otdf_sdk_mgr.bench_prepare.get_sdk_dirs")
    def test_release_installs_into_the_slugged_directory(self, mock_dirs, mock_release, tmp_path):
        """Without `dist_name`, install_release would pick its own directory.

        `check_collision` and `installed_tag` both reason about the slug, so
        the install has to land there too.
        """
        mock_dirs.return_value = {"js": tmp_path / "js"}
        mock_release.return_value = tmp_path / "js" / "dist" / "v0.4.0"

        identity = install_artifact("js", self._artifact())

        mock_release.assert_called_once_with("js", "0.4.0", dist_name="v0.4.0")
        assert identity.installed_tag == "v0.4.0"
        assert identity.installation_method == "release"
        assert identity.installed_path == str((tmp_path / "js" / "dist" / "v0.4.0").resolve())

    @patch("otdf_sdk_mgr.bench_prepare.install_release")
    @patch("otdf_sdk_mgr.bench_prepare.get_sdk_dirs")
    def test_install_error_becomes_bench_prepare_error(self, mock_dirs, mock_release, tmp_path):
        """InstallError is not a BenchPrepareError; unwrapped, it escaped as a traceback."""
        from otdf_sdk_mgr.installers import InstallError

        mock_dirs.return_value = {"js": tmp_path / "js"}
        mock_release.side_effect = InstallError("npm install failed")

        with pytest.raises(BenchPrepareError, match="npm install failed"):
            install_artifact("js", self._artifact())


class TestDistReuse:
    """An existing dist directory is evidence of a build, not of *this* build."""

    @pytest.fixture(autouse=True)
    def _sdk_dirs(self, tmp_path: Path, isolated_git: None):
        with patch("otdf_sdk_mgr.bench_prepare.get_sdk_dirs", return_value={"go": tmp_path / "go"}):
            yield

    def _artifact(self, commit_sha: str, alias: str = "main", tag: str = "main"):
        return ResolvedArtifact(
            requested_alias=alias,
            repository="https://github.com/opentdf/platform.git",
            commit_sha=commit_sha,
            tag=tag,
            is_head=True,
            is_release=False,
        )

    def _dist(self, tmp_path: Path, recorded: str | None) -> Path:
        dist = tmp_path / "go" / "dist" / "main"
        dist.mkdir(parents=True)
        if recorded is not None:
            (dist / ".version").write_text(f"ref=main\nsha={recorded}\n")
        return dist

    def _checkout(self, tmp_path: Path, slug: str = "main") -> str:
        """The source checkout cmd_tip would leave behind; returns its commit."""
        checkout = tmp_path / "go" / "src" / slug
        checkout.mkdir(parents=True)
        _git("init", "-q", cwd=checkout)
        _git("commit", "-q", "--allow-empty", "-m", "built", cwd=checkout)
        return _git("rev-parse", "HEAD", cwd=checkout)

    def _tip(self, tmp_path: Path):
        """A cmd_tip that builds the checked-out source into dist/<slug>."""

        def tip(sdks, ref):
            (tmp_path / "go" / "dist" / dist_slug(expand_pr_shorthand(ref))).mkdir(
                parents=True, exist_ok=True
            )

        return tip

    @patch("otdf_sdk_mgr.bench_prepare.cmd_tip")
    def test_dist_built_from_another_commit_is_rebuilt(self, mock_tip, tmp_path):
        """Reusing it would label the old build with the new commit.

        `main` moves. A dist left by yesterday's run is a different binary, and
        adopting it silently attributes today's SHA to yesterday's code — the
        manifest, the report and the verdict would all agree, and all be wrong.
        """
        dist = self._dist(tmp_path, recorded="0" * 40)
        sha = self._checkout(tmp_path)
        mock_tip.side_effect = self._tip(tmp_path)

        identity = install_artifact("go", self._artifact(sha))

        mock_tip.assert_called_once_with(["go"], ref="main")
        assert identity.commit_sha == sha
        assert (dist / ".version").read_text() == f"ref=main\nsha={sha}\n"

    @pytest.mark.parametrize(
        "version_file",
        # None, or a go release's bare `module@tag`: neither records a commit.
        [None, "github.com/opentdf/platform/otdfctl@v0.38.0\n"],
    )
    @patch("otdf_sdk_mgr.bench_prepare.cmd_tip")
    def test_dist_of_unknown_provenance_is_discarded_and_rebuilt(
        self, mock_tip, tmp_path, version_file
    ):
        """No recorded commit means no evidence; rebuild rather than guess.

        The old contents go first: cmd_tip reuses a full SHA's dist as it
        finds it, so a leftover file would ride along into the new build.
        """
        dist = self._dist(tmp_path, recorded=None)
        if version_file is not None:
            (dist / ".version").write_text(version_file)
        (dist / "leftover").write_text("")
        sha = self._checkout(tmp_path)
        mock_tip.side_effect = self._tip(tmp_path)

        install_artifact("go", self._artifact(sha))

        mock_tip.assert_called_once()
        assert not (dist / "leftover").exists()

    @patch("otdf_sdk_mgr.bench_prepare.cmd_tip")
    def test_dist_recorded_at_this_commit_is_reused(self, mock_tip, tmp_path):
        self._dist(tmp_path, recorded="a" * 40)

        identity = install_artifact("go", self._artifact("a" * 40))

        mock_tip.assert_not_called()
        assert identity.commit_sha == "a" * 40

    @patch("otdf_sdk_mgr.bench_prepare.cmd_tip")
    def test_ref_that_moved_before_the_build_is_an_error(self, mock_tip, tmp_path):
        """cmd_tip checks out the alias, so a branch that moved since resolution
        builds newer code than the resolved SHA. Recording the resolved SHA
        would mislabel the build; the run must not proceed as if it were."""
        dist = self._dist(tmp_path, recorded=None)
        built = self._checkout(tmp_path)
        mock_tip.side_effect = self._tip(tmp_path)

        with pytest.raises(BenchPrepareError, match="moved during preparation"):
            install_artifact("go", self._artifact("f" * 40))

        # What is on disk is recorded truthfully, so a rerun that resolves the
        # branch to its new tip reuses this build instead of compiling again.
        assert (dist / ".version").read_text() == f"ref=main\nsha={built}\n"

    @patch("otdf_sdk_mgr.bench_prepare.cmd_tip")
    def test_cmd_tip_builds_the_alias_into_the_slugged_directory(self, mock_tip, tmp_path):
        """A PR arm builds `pr:123`, not its resolved tag `pull-123`."""
        sha = self._checkout(tmp_path, slug="refs--pull--123--head")
        mock_tip.side_effect = self._tip(tmp_path)

        identity = install_artifact("go", self._artifact(sha, alias="pr:123", tag="pull-123"))

        mock_tip.assert_called_once_with(["go"], ref="pr:123")
        assert identity.installed_tag == "refs--pull--123--head"
        assert identity.installation_method == "source"
        assert identity.commit_sha == sha

    @patch("otdf_sdk_mgr.bench_prepare.cmd_tip")
    def test_git_stderr_reaches_the_error(self, mock_tip, tmp_path):
        """checkout.py captures git's stderr; `str(e)` alone drops it."""
        mock_tip.side_effect = subprocess.CalledProcessError(
            128, ["git", "worktree", "add"], stderr="fatal: invalid reference: nope"
        )

        with pytest.raises(BenchPrepareError, match="invalid reference: nope"):
            install_artifact("go", self._artifact("a" * 40))

    @patch("otdf_sdk_mgr.bench_prepare.cmd_tip")
    def test_build_that_lands_elsewhere_is_an_error_not_a_success(self, mock_tip, tmp_path):
        """If the slug rules ever diverge again, say so rather than proceed."""
        (tmp_path / "go" / "dist").mkdir(parents=True)
        mock_tip.return_value = None  # builds nothing where we expect it

        with pytest.raises(BenchPrepareError, match="slug rules have diverged"):
            install_artifact("go", self._artifact("a" * 40))
