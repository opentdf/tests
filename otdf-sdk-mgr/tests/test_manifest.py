"""Tests for manifest.py - installation manifest and artifact identity."""

from pathlib import Path
from unittest.mock import patch

import pytest

from otdf_sdk_mgr.manifest import (
    MANIFEST_VERSION,
    ArtifactIdentity,
    InstallationManifest,
    PreparationStatus,
    ResolvedArtifact,
    check_collision,
    is_neutral_preparation,
    repeated_builds,
)


def _identity(alias: str, commit_sha: str | None, tag: str | None = None) -> ArtifactIdentity:
    return ArtifactIdentity(
        requested_alias=alias,
        repository="https://github.com/opentdf/web-sdk.git",
        commit_sha=commit_sha,
        installed_tag=tag or alias,
        installed_path=f"/sdk/js/dist/{tag or alias}",
        installation_method="release",
    )


def _npm_only_release(version: str) -> ResolvedArtifact:
    """A js release on npm with no git tag: resolution finds no commit."""
    return ResolvedArtifact(
        requested_alias=version,
        repository="https://github.com/opentdf/web-sdk.git",
        commit_sha=None,
        tag=version.removeprefix("v"),
        is_head=False,
        is_release=True,
    )


class TestArtifactIdentity:
    def test_to_dict_from_dict_roundtrip(self):
        identity = ArtifactIdentity(
            requested_alias="main",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="abc123def456",
            installed_tag="main",
            installed_path="/path/to/dist/main",
            installation_method="source",
            build_settings={"GO_VERSION": "1.22"},
        )
        d = identity.to_dict()
        restored = ArtifactIdentity.from_dict(d)
        assert restored == identity

    def test_unknown_commit_and_path_round_trip_as_null(self):
        """Not as the string "None", which `str(d[key])` would make of them."""
        identity = ArtifactIdentity(
            requested_alias="v0.4.0",
            repository="https://github.com/opentdf/web-sdk.git",
            commit_sha=None,
            installed_tag="v0.4.0",
            installed_path=None,
            installation_method="release",
        )

        d = identity.to_dict()

        assert d["commit_sha"] is None
        assert d["installed_path"] is None
        assert ArtifactIdentity.from_dict(d) == identity

    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            ("installation_method", "bogus", "installation_method"),
            ("requested_alias", None, "requested_alias"),
            ("commit_sha", 123, "commit_sha"),
            ("build_settings", {"a": 1}, "build_settings"),
        ],
    )
    def test_from_dict_rejects_mistyped_fields(self, field, value, error):
        d = _identity("v0.4.0", "abc123").to_dict()
        d[field] = value

        with pytest.raises(ValueError, match=error):
            ArtifactIdentity.from_dict(d)

    def test_from_dict_rejects_a_missing_commit(self):
        """Null says "unknown"; absent says the file is malformed."""
        d = _identity("v0.4.0", "abc123").to_dict()
        del d["commit_sha"]

        with pytest.raises(ValueError, match="commit_sha"):
            ArtifactIdentity.from_dict(d)

    def test_default_build_settings(self):
        identity = ArtifactIdentity(
            requested_alias="v0.29.0",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="def789",
            installed_tag="v0.29.0",
            installed_path="/path/to/dist/v0.29.0",
            installation_method="release",
        )
        assert identity.build_settings == {}


class TestInstallationManifest:
    def test_to_dict_from_dict_roundtrip(self):
        manifest = InstallationManifest(
            platform=ArtifactIdentity(
                requested_alias="main",
                repository="https://github.com/opentdf/platform.git",
                commit_sha="platform123",
                installed_tag="main",
                installed_path="/path/to/platform/main",
                installation_method="source",
            ),
            otdfctl=ArtifactIdentity(
                requested_alias="v0.30.0",
                repository="https://github.com/opentdf/platform.git",
                commit_sha="otdfctl456",
                installed_tag="v0.30.0",
                installed_path="/path/to/go/v0.30.0",
                installation_method="release",
            ),
            sdk_arms=[
                ArtifactIdentity(
                    requested_alias="v0.29.0",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha="baseline789",
                    installed_tag="v0.29.0",
                    installed_path="/path/to/go/v0.29.0",
                    installation_method="release",
                ),
                ArtifactIdentity(
                    requested_alias="main",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha="candidate123",
                    installed_tag="main",
                    installed_path="/path/to/go/main",
                    installation_method="source",
                ),
            ],
            status=PreparationStatus.SUCCESS,
            metadata={"runner": "ubuntu-latest"},
        )

        d = manifest.to_dict()
        restored = InstallationManifest.from_dict(d)

        assert restored.schema_version == manifest.schema_version
        assert restored.platform == manifest.platform
        assert restored.otdfctl == manifest.otdfctl
        assert restored.sdk_arms == manifest.sdk_arms
        assert restored.status == manifest.status
        assert restored.metadata == manifest.metadata

    def test_write_read_roundtrip(self, tmp_path: Path):
        manifest = InstallationManifest(
            sdk_arms=[
                ArtifactIdentity(
                    requested_alias="main",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha="abc123",
                    installed_tag="main",
                    installed_path="/path/to/dist/main",
                    installation_method="source",
                )
            ],
            status=PreparationStatus.SUCCESS,
        )

        path = tmp_path / "manifest.json"
        manifest.write(path)

        assert path.exists()
        restored = InstallationManifest.read(path)
        assert restored.sdk_arms == manifest.sdk_arms
        assert restored.status == manifest.status

    def test_write_creates_missing_directories_and_leaves_no_temp_file(self, tmp_path: Path):
        path = tmp_path / "new" / "dir" / "manifest.json"

        InstallationManifest(status=PreparationStatus.FAILED).write(path)

        assert [p.name for p in path.parent.iterdir()] == ["manifest.json"]

    def test_a_write_cut_short_leaves_the_previous_file_intact(self, tmp_path: Path):
        """Truncated JSON would read as neither the old run nor the new one."""
        path = tmp_path / "manifest.json"
        InstallationManifest(status=PreparationStatus.SUCCESS).write(path)
        before = path.read_bytes()
        real_write_text = Path.write_text

        def half_then_full_disk(self: Path, data: str, *args, **kwargs) -> int:
            real_write_text(self, data[: len(data) // 2], *args, **kwargs)
            raise OSError(28, "No space left on device")

        with (
            patch.object(Path, "write_text", half_then_full_disk),
            pytest.raises(OSError, match="No space"),
        ):
            InstallationManifest(status=PreparationStatus.FAILED).write(path)

        assert path.read_bytes() == before

    def test_status_is_required(self):
        """A manifest nobody marked as a success must not read as one."""
        with pytest.raises(TypeError):
            InstallationManifest()  # type: ignore[call-arg]

    def test_from_dict_rejects_a_missing_status(self):
        with pytest.raises(ValueError, match="no status"):
            InstallationManifest.from_dict({"schema_version": MANIFEST_VERSION})

    def test_from_dict_rejects_an_unknown_status(self):
        d = InstallationManifest(status=PreparationStatus.SUCCESS).to_dict()
        d["status"] = "SUCCESS"

        with pytest.raises(ValueError, match="PreparationStatus"):
            InstallationManifest.from_dict(d)

    def test_from_dict_rejects_an_arm_that_is_not_an_object(self):
        d = InstallationManifest(status=PreparationStatus.SUCCESS).to_dict()
        d["sdk_arms"] = ["main"]

        with pytest.raises(ValueError, match=r"sdk_arms\[0\]"):
            InstallationManifest.from_dict(d)

    @pytest.mark.parametrize("version", [None, "v0", "v2alpha1"])
    def test_from_dict_rejects_other_schema_versions(self, version):
        d = InstallationManifest(status=PreparationStatus.SUCCESS).to_dict()
        d["schema_version"] = version

        with pytest.raises(ValueError, match="schema_version"):
            InstallationManifest.from_dict(d)

    def test_neutral_status_with_error(self):
        manifest = InstallationManifest(
            status=PreparationStatus.NEUTRAL,
            status_message="All requests resolved to the same commit",
        )
        d = manifest.to_dict()
        assert d["status"] == "neutral"
        assert d["status_message"] == "All requests resolved to the same commit"


class TestResolvedArtifact:
    def test_installation_method_release(self):
        artifact = ResolvedArtifact(
            requested_alias="v0.29.0",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="abc123",
            tag="v0.29.0",
            is_head=False,
            is_release=True,
        )
        assert artifact.installation_method == "release"

    def test_installation_method_source(self):
        artifact = ResolvedArtifact(
            requested_alias="main",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="def456",
            tag="main",
            is_head=True,
            is_release=False,
        )
        assert artifact.installation_method == "source"


class TestCheckCollision:
    def test_no_collision(self):
        resolved = [
            ResolvedArtifact(
                requested_alias="v0.29.0",
                repository="https://github.com/opentdf/platform.git",
                commit_sha="abc",
                tag="v0.29.0",
                is_head=False,
                is_release=True,
            ),
            ResolvedArtifact(
                requested_alias="main",
                repository="https://github.com/opentdf/platform.git",
                commit_sha="def",
                tag="main",
                is_head=True,
                is_release=False,
            ),
        ]
        assert check_collision(resolved) is None

    def test_collision_detected(self):
        resolved = [
            ResolvedArtifact(
                requested_alias="v0.29.0",
                repository="https://github.com/opentdf/platform.git",
                commit_sha="abc",
                tag="v0.29.0",
                is_head=False,
                is_release=True,
            ),
            ResolvedArtifact(
                requested_alias="otdfctl/v0.29.0",
                repository="https://github.com/opentdf/platform.git",
                commit_sha="def",
                tag="v0.29.0",  # same tag, different alias
                is_head=False,
                is_release=True,
            ),
        ]
        error = check_collision(resolved)
        assert error is not None
        assert "Colliding installed paths" in error
        assert "v0.29.0" in error

    def test_an_unknown_commit_is_named_as_such(self):
        known = ResolvedArtifact(
            requested_alias="v0.4.0",
            repository="https://github.com/opentdf/web-sdk.git",
            commit_sha="abcdef123456",
            tag="v0.4.0",
            is_head=False,
            is_release=True,
        )

        error = check_collision([known, _npm_only_release("0.4.0")])

        assert error is not None
        assert "v0.4.0: 0.4.0 at an unknown commit; v0.4.0 at abcdef12" in error


class TestIsNeutralPreparation:
    def test_neutral_same_commit(self):
        resolved = [
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
        ]
        assert is_neutral_preparation(resolved)

    def test_not_neutral_different_commits(self):
        resolved = [
            ResolvedArtifact(
                requested_alias="v0.29.0",
                repository="https://github.com/opentdf/platform.git",
                commit_sha="commit_a",
                tag="v0.29.0",
                is_head=False,
                is_release=True,
            ),
            ResolvedArtifact(
                requested_alias="main",
                repository="https://github.com/opentdf/platform.git",
                commit_sha="commit_b",
                tag="main",
                is_head=True,
                is_release=False,
            ),
        ]
        assert not is_neutral_preparation(resolved)

    def test_not_neutral_single_artifact(self):
        resolved = [
            ResolvedArtifact(
                requested_alias="main",
                repository="https://github.com/opentdf/platform.git",
                commit_sha="abc",
                tag="main",
                is_head=True,
                is_release=False,
            )
        ]
        assert not is_neutral_preparation(resolved)

    def test_not_neutral_empty(self):
        assert not is_neutral_preparation([])

    def test_releases_with_unknown_commits_are_not_one_build(self):
        """Two npm-only releases share a missing commit, not a build.

        Comparing commits alone made `v0.3.0 v0.4.0` NEUTRAL: nothing built,
        exit 0, and a benchmark that silently measured nothing.
        """
        assert not is_neutral_preparation(
            [_npm_only_release("v0.3.0"), _npm_only_release("v0.4.0")]
        )

    def test_one_release_with_an_unknown_commit_asked_for_twice_is_neutral(self):
        assert is_neutral_preparation([_npm_only_release("v0.4.0"), _npm_only_release("0.4.0")])


class TestRepeatedBuilds:
    def test_arms_at_one_commit_are_grouped(self):
        arms = [
            _identity("v0.38.0", "aaa"),
            _identity("main", "aaa"),
            _identity("pr:123", "bbb"),
        ]

        assert repeated_builds(arms) == [["v0.38.0", "main"]]

    def test_distinct_builds_are_not(self):
        assert repeated_builds([_identity("v0.38.0", "aaa"), _identity("main", "bbb")]) == []

    def test_unknown_commits_group_by_directory(self):
        arms = [
            _identity("v0.3.0", None),
            _identity("v0.4.0", None),
            _identity("0.4.0", None, tag="v0.4.0"),
        ]

        assert repeated_builds(arms) == [["v0.4.0", "0.4.0"]]
