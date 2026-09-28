"""Tests for manifest.py - installation manifest and artifact identity."""

from pathlib import Path


from otdf_sdk_mgr.manifest import (
    ArtifactIdentity,
    InstallationManifest,
    PreparationStatus,
    ResolvedArtifact,
    check_collision,
    is_neutral_preparation,
)


class TestArtifactIdentity:
    def test_to_dict_from_dict_roundtrip(self):
        identity = ArtifactIdentity(
            requested_alias="go@main",
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

    def test_default_build_settings(self):
        identity = ArtifactIdentity(
            requested_alias="go@v0.29.0",
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
                requested_alias="platform@main",
                repository="https://github.com/opentdf/platform.git",
                commit_sha="platform123",
                installed_tag="main",
                installed_path="/path/to/platform/main",
                installation_method="source",
            ),
            otdfctl=ArtifactIdentity(
                requested_alias="go@v0.30.0",
                repository="https://github.com/opentdf/platform.git",
                commit_sha="otdfctl456",
                installed_tag="v0.30.0",
                installed_path="/path/to/go/v0.30.0",
                installation_method="release",
            ),
            sdk_arms=[
                ArtifactIdentity(
                    requested_alias="go@v0.29.0",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha="baseline789",
                    installed_tag="v0.29.0",
                    installed_path="/path/to/go/v0.29.0",
                    installation_method="release",
                ),
                ArtifactIdentity(
                    requested_alias="go@main",
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
                    requested_alias="go@main",
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

    def test_is_same_commit_true(self):
        manifest = InstallationManifest(
            sdk_arms=[
                ArtifactIdentity(
                    requested_alias="go@v0.29.0",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha="same_commit",
                    installed_tag="v0.29.0",
                    installed_path="/path/to/v0.29.0",
                    installation_method="release",
                ),
                ArtifactIdentity(
                    requested_alias="go@v0.29.1",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha="same_commit",
                    installed_tag="v0.29.1",
                    installed_path="/path/to/v0.29.1",
                    installation_method="release",
                ),
            ]
        )
        assert manifest.is_same_commit()

    def test_is_same_commit_false(self):
        manifest = InstallationManifest(
            sdk_arms=[
                ArtifactIdentity(
                    requested_alias="go@v0.29.0",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha="commit_a",
                    installed_tag="v0.29.0",
                    installed_path="/path/to/v0.29.0",
                    installation_method="release",
                ),
                ArtifactIdentity(
                    requested_alias="go@main",
                    repository="https://github.com/opentdf/platform.git",
                    commit_sha="commit_b",
                    installed_tag="main",
                    installed_path="/path/to/main",
                    installation_method="source",
                ),
            ]
        )
        assert not manifest.is_same_commit()

    def test_is_same_commit_empty(self):
        manifest = InstallationManifest()
        assert not manifest.is_same_commit()

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
            requested_alias="go@v0.29.0",
            repository="https://github.com/opentdf/platform.git",
            commit_sha="abc123",
            tag="v0.29.0",
            is_head=False,
            is_release=True,
        )
        assert artifact.installation_method == "release"

    def test_installation_method_source(self):
        artifact = ResolvedArtifact(
            requested_alias="go@main",
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
                requested_alias="go@v0.29.0",
                repository="https://github.com/opentdf/platform.git",
                commit_sha="abc",
                tag="v0.29.0",
                is_head=False,
                is_release=True,
            ),
            ResolvedArtifact(
                requested_alias="go@main",
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
                requested_alias="go@v0.29.0",
                repository="https://github.com/opentdf/platform.git",
                commit_sha="abc",
                tag="v0.29.0",
                is_head=False,
                is_release=True,
            ),
            ResolvedArtifact(
                requested_alias="go@otdfctl/v0.29.0",
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


class TestIsNeutralPreparation:
    def test_neutral_same_commit(self):
        resolved = [
            ResolvedArtifact(
                requested_alias="go@v0.29.0",
                repository="https://github.com/opentdf/platform.git",
                commit_sha="same_commit",
                tag="v0.29.0",
                is_head=False,
                is_release=True,
            ),
            ResolvedArtifact(
                requested_alias="go@main",
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
                requested_alias="go@v0.29.0",
                repository="https://github.com/opentdf/platform.git",
                commit_sha="commit_a",
                tag="v0.29.0",
                is_head=False,
                is_release=True,
            ),
            ResolvedArtifact(
                requested_alias="go@main",
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
                requested_alias="go@main",
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
