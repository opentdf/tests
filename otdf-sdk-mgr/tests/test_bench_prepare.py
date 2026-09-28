"""Tests for bench_prepare.py - ordered resolution and installation."""

from pathlib import Path
from unittest.mock import patch

import pytest

from otdf_sdk_mgr.bench_prepare import (
    BenchPrepareError,
    install_artifact,
    prepare_benchmark,
    resolve_ordered,
)
from otdf_sdk_mgr.manifest import (
    ArtifactIdentity,
    PreparationStatus,
    ResolvedArtifact,
    dist_slug_for,
)


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
                "sha": "abc123",
                "tag": "v0.29.0",
                "release": "otdfctl/v0.29.0",
            },
            {
                "sdk": "go",
                "alias": "main",
                "sha": "def456",
                "tag": "main",
                "head": True,
            },
        ]

        resolved, error = resolve_ordered("go", ["v0.29.0", "main"])

        assert error is None
        assert len(resolved) == 2
        assert resolved[0].requested_alias == "v0.29.0"
        assert resolved[0].commit_sha == "abc123"
        assert resolved[0].is_release is True
        assert resolved[1].requested_alias == "main"
        assert resolved[1].commit_sha == "def456"
        assert resolved[1].is_head is True

    @patch("otdf_sdk_mgr.bench_prepare.resolve")
    @patch("otdf_sdk_mgr.bench_prepare.expand_pr_shorthand")
    def test_resolve_expands_pr_shorthand(self, mock_expand, mock_resolve):
        mock_expand.side_effect = lambda x: "refs/pull/123/head" if x == "pr:123" else x
        mock_resolve.return_value = {
            "sdk": "go",
            "alias": "pr:123",
            "sha": "abc123",
            "tag": "pull-123",
            "head": True,
            "pr": "123",
        }

        resolved, error = resolve_ordered("go", ["pr:123"])

        assert error is None
        assert len(resolved) == 1
        assert resolved[0].requested_alias == "pr:123"
        mock_expand.assert_called_with("pr:123")

    @patch("otdf_sdk_mgr.bench_prepare.resolve")
    @patch("otdf_sdk_mgr.bench_prepare.expand_pr_shorthand")
    def test_resolve_same_commit_preserves_aliases(self, mock_expand, mock_resolve):
        # Both aliases resolve to the same commit
        mock_expand.side_effect = lambda x: x
        mock_resolve.side_effect = [
            {
                "sdk": "go",
                "alias": "v0.29.0",
                "sha": "same_commit",
                "tag": "v0.29.0",
                "release": "otdfctl/v0.29.0",
            },
            {
                "sdk": "go",
                "alias": "main",
                "sha": "same_commit",
                "tag": "main",
                "head": True,
            },
        ]

        resolved, error = resolve_ordered("go", ["v0.29.0", "main"])

        assert error is None
        assert len(resolved) == 2  # Both preserved
        assert resolved[0].commit_sha == resolved[1].commit_sha

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
                    commit_sha="same_commit",
                    tag="v0.29.0",
                    is_head=False,
                    is_release=True,
                ),
                ResolvedArtifact(
                    requested_alias="main",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha="same_commit",
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
        assert [arm.commit_sha for arm in manifest.sdk_arms] == ["same_commit"] * 2
        assert [arm.requested_alias for arm in manifest.sdk_arms] == ["v0.29.0", "main"]
        # Empty unconditionally, not "empty because the directory happens to be
        # absent". A leftover `dist/main` from an earlier run is common, and
        # naming it would claim a provenance this preparation never checked.
        assert all(arm.installed_path == "" for arm in manifest.sdk_arms)

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_resolution_failure(self, mock_resolve, mock_install, tmp_path):
        mock_resolve.return_value = ([], "Failed to resolve go@bogus: ref not found")

        manifest = prepare_benchmark("go", ["bogus"], manifest_path=tmp_path / "m.json")

        assert manifest.status == PreparationStatus.FAILED
        assert "Failed to resolve" in manifest.status_message
        mock_install.assert_not_called()

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_namespaced_and_plain_tags_collide_on_the_dist_path(
        self, mock_resolve, mock_install, tmp_path
    ):
        """`otdfctl/v0.24.0` and `v0.24.0` are distinct tags and one directory.

        Resolution flattens the namespaced tag to `otdfctl--v0.24.0`, and
        `cmd_tip` then strips the `otdfctl--` prefix, so both arms build into
        `dist/v0.24.0`. Bucketing on the raw tag sees two different strings and
        waves this through; the second install silently adopts the first's
        directory and the run measures one commit against itself.
        """
        mock_resolve.return_value = (
            [
                ResolvedArtifact(
                    requested_alias="v0.24.0",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha="aaaaaaa",
                    tag="v0.24.0",
                    is_head=False,
                    is_release=True,
                ),
                ResolvedArtifact(
                    requested_alias="otdfctl/v0.24.0",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha="bbbbbbb",
                    tag="otdfctl--v0.24.0",
                    is_head=False,
                    is_release=True,
                ),
            ],
            None,
        )

        manifest = prepare_benchmark(
            "go", ["v0.24.0", "otdfctl/v0.24.0"], manifest_path=tmp_path / "m.json"
        )

        assert manifest.status == PreparationStatus.FAILED
        assert "Colliding installed paths" in manifest.status_message
        # The commits are named because they are what makes it a collision:
        # one directory cannot hold both.
        assert "v0.24.0: v0.24.0 at aaaaaaa; otdfctl/v0.24.0 at bbbbbbb" in (
            manifest.status_message
        )
        mock_install.assert_not_called()

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_one_commit_under_colliding_tags_is_neutral_not_failed(
        self, mock_resolve, mock_install, tmp_path
    ):
        """Same commit wins over same path: neutral, not an error.

        Two aliases that collapse to one commit *and* one dist directory are the
        degenerate case of a same-commit run, which the spec makes an explicit
        neutral outcome. Checking collisions first would report FAILED and hide
        the reason the benchmark is meaningless.
        """
        mock_resolve.return_value = (
            [
                ResolvedArtifact(
                    requested_alias="v0.24.0",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha="onecommit",
                    tag="v0.24.0",
                    is_head=False,
                    is_release=True,
                ),
                ResolvedArtifact(
                    requested_alias="otdfctl/v0.24.0",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha="onecommit",
                    tag="otdfctl--v0.24.0",
                    is_head=False,
                    is_release=True,
                ),
            ],
            None,
        )

        manifest = prepare_benchmark(
            "go", ["v0.24.0", "otdfctl/v0.24.0"], manifest_path=tmp_path / "m.json"
        )

        assert manifest.status == PreparationStatus.NEUTRAL
        assert "onecommi" in manifest.status_message
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
            commit_sha="aaaaaaa",
            tag="v0.24.0",
            is_head=False,
            is_release=True,
        )
        main = ResolvedArtifact(
            requested_alias="main",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="bbbbbbb",
            tag="main",
            is_head=True,
            is_release=False,
        )
        mock_resolve.side_effect = [([arm, main], None), ([arm], None)]
        mock_install.return_value = _identity("v0.24.0", "aaaaaaa")

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

        `otdfctl/v0.24.0` and `v0.24.0` are distinct commits sharing one dist
        path, so installing both means the provisioning CLI overwrites a build
        the run is measuring -- and nothing afterwards can tell which one is
        in the directory.
        """
        arm = ResolvedArtifact(
            requested_alias="v0.24.0",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="aaaaaaa",
            tag="v0.24.0",
            is_head=False,
            is_release=True,
        )
        main = ResolvedArtifact(
            requested_alias="main",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="bbbbbbb",
            tag="main",
            is_head=True,
            is_release=False,
        )
        pin = ResolvedArtifact(
            requested_alias="otdfctl/v0.24.0",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="ccccccc",
            tag="otdfctl--v0.24.0",
            is_head=False,
            is_release=True,
        )
        mock_resolve.side_effect = [([arm, main], None), ([pin], None)]

        manifest = prepare_benchmark(
            "go",
            ["v0.24.0", "main"],
            otdfctl_ref="otdfctl/v0.24.0",
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
            commit_sha="bbbbbbb",
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
            commit_sha="aaaaaaa",
            tag="v0.24.0",
            is_head=False,
            is_release=True,
        )
        main = ResolvedArtifact(
            requested_alias="main",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="bbbbbbb",
            tag="main",
            is_head=True,
            is_release=False,
        )
        pin = ResolvedArtifact(
            requested_alias="v0.24.0",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="ccccccc",
            tag="v0.24.0",
            is_head=False,
            is_release=True,
        )
        mock_resolve.side_effect = [([arm, main], None), ([pin], None)]
        mock_install.return_value = _identity("v0.24.0", "ccccccc")

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
                    commit_sha="abc123",
                    tag="v0.29.0",
                    is_head=False,
                    is_release=True,
                ),
                ResolvedArtifact(
                    requested_alias="main",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha="def456",
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
                commit_sha="abc123",
                installed_tag="v0.29.0",
                installed_path="/path/to/v0.29.0",
                installation_method="release",
            ),
            ArtifactIdentity(
                requested_alias="main",
                repository="https://github.com/opentdf/platform.git",
                commit_sha="def456",
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

    @patch("otdf_sdk_mgr.bench_prepare.install_artifact")
    @patch("otdf_sdk_mgr.bench_prepare.resolve_ordered")
    def test_install_failure(self, mock_resolve, mock_install, tmp_path):
        mock_resolve.return_value = (
            [
                ResolvedArtifact(
                    requested_alias="v0.29.0",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha="abc123",
                    tag="v0.29.0",
                    is_head=False,
                    is_release=True,
                ),
            ],
            None,
        )

        mock_install.side_effect = BenchPrepareError("Installation failed")

        manifest = prepare_benchmark("go", ["v0.29.0"], manifest_path=tmp_path / "m.json")

        assert manifest.status == PreparationStatus.PARTIAL
        assert "Installation failed" in manifest.status_message


class TestDistSlugFor:
    """The dist directory an artifact will occupy, and who decides it."""

    def test_source_build_slug_matches_cmd_tip_not_the_resolved_tag(self):
        """A PR arm's tag and its build directory are different strings.

        `resolve` reports `pr:123` as the tag `pull-123`, but `cmd_tip` expands
        the ref and builds into `refs--pull--123--head`. Deriving the directory
        from the tag points at somewhere that never gets created, so the build
        looks like it failed and every PR arm reports PARTIAL.
        """
        artifact = ResolvedArtifact(
            requested_alias="pr:123",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="abc123",
            tag="pull-123",
            is_head=True,
            is_release=False,
        )

        assert dist_slug_for(artifact) == "refs--pull--123--head"

    def test_release_slug_comes_from_the_tag_not_the_alias(self):
        """A release alias may be mutable; its resolved tag is not."""
        artifact = ResolvedArtifact(
            requested_alias="latest",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="abc123",
            tag="otdfctl--v0.24.0",
            is_head=False,
            is_release=True,
        )

        assert dist_slug_for(artifact) == "v0.24.0"


class TestDistReuse:
    """An existing dist directory is evidence of a build, not of *this* build."""

    def _artifact(self) -> ResolvedArtifact:
        return ResolvedArtifact(
            requested_alias="main",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="newcommit",
            tag="main",
            is_head=True,
            is_release=False,
        )

    def _dist(self, tmp_path, recorded: str | None) -> Path:
        dist = tmp_path / "go" / "dist" / "main"
        dist.mkdir(parents=True)
        if recorded is not None:
            (dist / ".version").write_text(f"ref=main\nsha={recorded}\n")
        return dist

    @patch("otdf_sdk_mgr.bench_prepare.cmd_tip")
    @patch("otdf_sdk_mgr.bench_prepare.get_sdk_dirs")
    def test_dist_built_from_another_commit_is_rebuilt(self, mock_dirs, mock_tip, tmp_path):
        """Reusing it would label the old build with the new commit.

        `main` moves. A dist left by yesterday's run is a different binary, and
        adopting it silently attributes today's SHA to yesterday's code — the
        manifest, the report and the verdict would all agree, and all be wrong.
        """
        mock_dirs.return_value = {"go": tmp_path / "go"}
        dist = self._dist(tmp_path, recorded="oldcommit")
        mock_tip.side_effect = lambda sdks, ref: dist.mkdir(parents=True, exist_ok=True)

        identity = install_artifact("go", self._artifact())

        mock_tip.assert_called_once()
        assert identity.commit_sha == "newcommit"
        assert (dist / ".version").read_text() == "ref=main\nsha=newcommit\n"

    @patch("otdf_sdk_mgr.bench_prepare.cmd_tip")
    @patch("otdf_sdk_mgr.bench_prepare.get_sdk_dirs")
    def test_dist_of_unknown_provenance_is_rebuilt(self, mock_dirs, mock_tip, tmp_path):
        """No `.version` means no evidence; rebuild rather than guess."""
        mock_dirs.return_value = {"go": tmp_path / "go"}
        dist = self._dist(tmp_path, recorded=None)
        mock_tip.side_effect = lambda sdks, ref: dist.mkdir(parents=True, exist_ok=True)

        install_artifact("go", self._artifact())

        mock_tip.assert_called_once()

    @patch("otdf_sdk_mgr.bench_prepare.cmd_tip")
    @patch("otdf_sdk_mgr.bench_prepare.get_sdk_dirs")
    def test_dist_recorded_at_this_commit_is_reused(self, mock_dirs, mock_tip, tmp_path):
        mock_dirs.return_value = {"go": tmp_path / "go"}
        self._dist(tmp_path, recorded="newcommit")

        identity = install_artifact("go", self._artifact())

        mock_tip.assert_not_called()
        assert identity.commit_sha == "newcommit"

    @patch("otdf_sdk_mgr.bench_prepare.cmd_tip")
    @patch("otdf_sdk_mgr.bench_prepare.get_sdk_dirs")
    def test_build_that_lands_elsewhere_is_an_error_not_a_success(
        self, mock_dirs, mock_tip, tmp_path
    ):
        """If the slug rules ever diverge again, say so rather than proceed."""
        mock_dirs.return_value = {"go": tmp_path / "go"}
        (tmp_path / "go" / "dist").mkdir(parents=True)
        mock_tip.return_value = None  # builds nothing where we expect it

        with pytest.raises(BenchPrepareError, match="slug rules have diverged"):
            install_artifact("go", self._artifact())
