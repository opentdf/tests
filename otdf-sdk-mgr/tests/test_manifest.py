"""Tests for manifest.py - installation manifest and artifact identity."""

import hashlib
import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from otdf_sdk_mgr.manifest import (
    ArtifactIdentity,
    InstallationManifest,
    ManifestError,
    PreparationStatus,
    ResolvedArtifact,
    check_collision,
    dist_slug_for,
    is_neutral_preparation,
    repeated_builds,
)

JS_REPO = "https://github.com/opentdf/web-sdk.git"
PLATFORM_REPO = "https://github.com/opentdf/platform.git"


def sha(label: str) -> str:
    """A full commit SHA standing for `label`: distinct labels, distinct commits."""
    return hashlib.sha1(label.encode()).hexdigest()


def _identity(
    alias: str,
    commit_sha: str | None,
    tag: str | None = None,
    *,
    installed: bool = True,
) -> ArtifactIdentity:
    return ArtifactIdentity(
        requested_alias=alias,
        repository=JS_REPO,
        commit_sha=commit_sha,
        installed_tag=tag or alias,
        installed_path=f"/sdk/js/dist/{tag or alias}" if installed else None,
        installation_method="release",
    )


def _resolved(
    alias: str, commit_sha: str | None, *, tag: str | None = None, release: bool = False
) -> ResolvedArtifact:
    return ResolvedArtifact(
        requested_alias=alias,
        repository=JS_REPO,
        commit_sha=commit_sha,
        tag=tag or alias,
        is_head=not release,
        is_release=release,
    )


def _npm_only_release(version: str) -> ResolvedArtifact:
    """A js release on npm with no git tag: resolution finds no commit."""
    return _resolved(version, None, tag=version.removeprefix("v"), release=True)


def _manifest(status: PreparationStatus, message: str = "why") -> InstallationManifest:
    """A manifest that `from_dict` accepts for `status`."""
    arms = {
        PreparationStatus.SUCCESS: [_identity("v0.29.0", sha("v0.29.0")), _identity("main", None)],
        PreparationStatus.NEUTRAL: [
            _identity(alias, sha("one"), installed=False) for alias in ("v0.29.0", "main")
        ],
        PreparationStatus.PARTIAL: [_identity("v0.29.0", sha("v0.29.0"))],
        PreparationStatus.FAILED: [],
    }[status]
    return InstallationManifest(
        sdk_arms=arms,
        status=status,
        status_message="" if status is PreparationStatus.SUCCESS else message,
        metadata={"sdk": "js"},
    )


# Every key, both installation methods, a null pin, a null commit, a SHA-256
# commit, and metadata.sdk, written out as readers outside this package see it.
GOLDEN = {
    "schema_version": "v1alpha1",
    "platform": {
        "requested_alias": "pr:42",
        "repository": "https://github.com/opentdf/platform.git",
        "commit_sha": "f00dcafef00dcafef00dcafef00dcafef00dcafe",
        "installed_tag": "refs--pull--42--head",
        "installed_path": "/xtest/platform/dist/refs--pull--42--head",
        "installation_method": "source",
        "build_settings": {},
    },
    "otdfctl": None,
    "sdk_arms": [
        {
            "requested_alias": "latest",
            "repository": "https://github.com/opentdf/web-sdk.git",
            "commit_sha": None,
            "installed_tag": "v0.4.0",
            "installed_path": "/xtest/sdk/js/dist/v0.4.0",
            "installation_method": "release",
            "build_settings": {},
        },
        {
            "requested_alias": "main",
            "repository": "https://github.com/opentdf/web-sdk.git",
            "commit_sha": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            "installed_tag": "main",
            "installed_path": "/xtest/sdk/js/dist/main",
            "installation_method": "source",
            "build_settings": {"NODE_VERSION": "22"},
        },
    ],
    "status": "success",
    "status_message": "",
    "metadata": {"sdk": "js", "runner": "ubuntu-latest"},
}


class TestArtifactIdentity:
    def test_to_dict_from_dict_roundtrip(self):
        identity = ArtifactIdentity(
            requested_alias="main",
            repository=PLATFORM_REPO,
            commit_sha=sha("main"),
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
        identity = _identity("v0.4.0", None, installed=False)

        d = identity.to_dict()

        assert d["commit_sha"] is None
        assert d["installed_path"] is None
        assert ArtifactIdentity.from_dict(d) == identity

    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            (
                "installation_method",
                "bogus",
                "installation_method must be one of release, source, not 'bogus'",
            ),
            ("requested_alias", None, "requested_alias must be a string, not None"),
            ("repository", None, "repository must be a string, not None"),
            ("commit_sha", 123, "commit_sha must be a string or null, not 123"),
            ("commit_sha", "abc1234", "commit_sha must be a full lowercase hex commit SHA"),
            ("installed_tag", 1, "installed_tag must be a string, not 1"),
            ("installed_tag", "", "installed_tag must not be empty"),
            ("installed_path", 1, "installed_path must be a string or null, not 1"),
            ("build_settings", {"a": 1}, "build_settings must map strings to strings"),
            ("build_settings", None, "build_settings must map strings to strings"),
        ],
    )
    def test_from_dict_rejects_mistyped_fields(self, field, value, error):
        """Each message names the field by its JSON path."""
        d = _identity("v0.4.0", sha("v0.4.0")).to_dict()
        d[field] = value

        with pytest.raises(ManifestError, match=rf"^sdk_arms\[2\]\.{error}"):
            ArtifactIdentity.from_dict(d, "sdk_arms[2]")

    @pytest.mark.parametrize("key", ["commit_sha", "installed_path"])
    def test_from_dict_says_a_nullable_key_is_missing(self, key):
        """Null says "unknown" or "not installed"; absent says the file is malformed."""
        d = _identity("v0.4.0", sha("v0.4.0")).to_dict()
        del d[key]

        with pytest.raises(ManifestError, match=rf"^platform is missing {key}$"):
            ArtifactIdentity.from_dict(d, "platform")

    def test_from_dict_reports_missing_and_unknown_keys_together(self):
        d = _identity("v0.4.0", sha("v0.4.0")).to_dict()
        del d["repository"]
        del d["build_settings"]
        d["colour"] = "blue"

        with pytest.raises(
            ManifestError,
            match=r"^identity is missing build_settings, repository and has unknown keys colour$",
        ):
            ArtifactIdentity.from_dict(d)

    @pytest.mark.parametrize("value", ["main", None, ["main"]])
    def test_from_dict_rejects_a_non_object(self, value):
        with pytest.raises(ManifestError, match=r"^sdk_arms\[0\] must be an object"):
            ArtifactIdentity.from_dict(value, "sdk_arms[0]")

    def test_default_build_settings(self):
        assert _identity("v0.29.0", sha("v0.29.0")).build_settings == {}


class TestConstructionInvariants:
    """Writers cannot build what `from_dict` rejects."""

    @pytest.mark.parametrize("commit_sha", [None, "a" * 40, "0123456789" * 6 + "abcd"])
    def test_full_commits_and_none_are_accepted(self, commit_sha):
        _identity("main", commit_sha)
        _resolved("main", commit_sha)

    @pytest.mark.parametrize(
        "commit_sha",
        ["abc1234", "", "A" * 40, "g" * 40, "a" * 39, "a" * 41, "a" * 63, "a" * 65],
    )
    def test_anything_else_is_not_a_commit(self, commit_sha):
        """`abc1234` and the commit it abbreviates must not count as two builds."""
        with pytest.raises(ManifestError, match="commit_sha must be a full lowercase hex"):
            _identity("main", commit_sha)
        with pytest.raises(ManifestError, match="commit_sha must be a full lowercase hex"):
            _resolved("main", commit_sha)

    def test_installed_tag_must_not_be_empty(self):
        with pytest.raises(ManifestError, match="installed_tag must not be empty"):
            ArtifactIdentity(
                requested_alias="main",
                repository=JS_REPO,
                commit_sha=None,
                installed_tag="",
                installed_path=None,
                installation_method="source",
            )

    def test_installation_method_must_be_known(self):
        with pytest.raises(ManifestError, match="must be one of release, source, not 'npm'"):
            ArtifactIdentity(
                requested_alias="main",
                repository=JS_REPO,
                commit_sha=None,
                installed_tag="main",
                installed_path=None,
                installation_method="npm",  # type: ignore[arg-type]
            )

    def test_manifest_error_is_a_value_error(self):
        """One `except ValueError` covers unparseable JSON and an invalid manifest."""
        assert issubclass(ManifestError, ValueError)


class TestInstallationManifest:
    def test_wire_shape(self):
        """The JSON, key for key, both ways: readers parse it without this package."""
        manifest = InstallationManifest(
            platform=ArtifactIdentity(
                requested_alias="pr:42",
                repository=PLATFORM_REPO,
                commit_sha="f00dcafe" * 5,
                installed_tag="refs--pull--42--head",
                installed_path="/xtest/platform/dist/refs--pull--42--head",
                installation_method="source",
            ),
            sdk_arms=[
                ArtifactIdentity(
                    requested_alias="latest",
                    repository=JS_REPO,
                    commit_sha=None,
                    installed_tag="v0.4.0",
                    installed_path="/xtest/sdk/js/dist/v0.4.0",
                    installation_method="release",
                ),
                ArtifactIdentity(
                    requested_alias="main",
                    repository=JS_REPO,
                    commit_sha="0123456789abcdef" * 4,
                    installed_tag="main",
                    installed_path="/xtest/sdk/js/dist/main",
                    installation_method="source",
                    build_settings={"NODE_VERSION": "22"},
                ),
            ],
            status=PreparationStatus.SUCCESS,
            metadata={"sdk": "js", "runner": "ubuntu-latest"},
        )

        assert manifest.to_dict() == GOLDEN
        assert InstallationManifest.from_dict(GOLDEN) == manifest

    @pytest.mark.parametrize(
        ("status", "wire"),
        [
            (PreparationStatus.SUCCESS, "success"),
            (PreparationStatus.NEUTRAL, "neutral"),
            (PreparationStatus.PARTIAL, "partial"),
            (PreparationStatus.FAILED, "failed"),
        ],
    )
    def test_each_status_and_its_message_round_trip(self, status, wire):
        manifest = _manifest(status, message=f"{wire} because")

        d = manifest.to_dict()

        assert d["status"] == wire
        assert d["status_message"] == manifest.status_message
        assert InstallationManifest.from_dict(d) == manifest

    def test_success_may_carry_a_warning(self):
        manifest = _manifest(PreparationStatus.SUCCESS)
        manifest.status_message = "v0.38.0 = main"

        assert InstallationManifest.from_dict(manifest.to_dict()) == manifest

    def test_schema_version_is_not_a_constructor_parameter(self):
        """A writer cannot stamp a version it does not write the shape of."""
        with pytest.raises(TypeError):
            InstallationManifest(status=PreparationStatus.FAILED, schema_version="v0")  # type: ignore[call-arg]

    def test_write_read_roundtrip(self, tmp_path: Path):
        manifest = _manifest(PreparationStatus.SUCCESS)
        path = tmp_path / "manifest.json"

        manifest.write(path)

        assert InstallationManifest.read(path) == manifest

    def test_write_creates_missing_directories_and_leaves_no_temp_file(self, tmp_path: Path):
        path = tmp_path / "new" / "dir" / "manifest.json"

        InstallationManifest(status=PreparationStatus.FAILED).write(path)

        assert [p.name for p in path.parent.iterdir()] == ["manifest.json"]

    def test_a_write_cut_short_leaves_the_previous_file_and_no_temp_file(self, tmp_path: Path):
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
        assert [p.name for p in tmp_path.iterdir()] == ["manifest.json"]

    @pytest.mark.parametrize("error", [OSError(13, "Permission denied"), KeyboardInterrupt()])
    def test_a_failed_rename_removes_the_temp_file(self, tmp_path: Path, error):
        """Ctrl-C included: a stray `.manifest.json.tmp` would sit there forever."""
        path = tmp_path / "manifest.json"
        InstallationManifest(status=PreparationStatus.SUCCESS).write(path)
        before = path.read_bytes()

        with (
            patch.object(Path, "replace", side_effect=error),
            pytest.raises(type(error)),
        ):
            InstallationManifest(status=PreparationStatus.FAILED).write(path)

        assert path.read_bytes() == before
        assert [p.name for p in tmp_path.iterdir()] == ["manifest.json"]

    def test_status_is_required(self):
        """A manifest nobody marked as a success must not read as one."""
        with pytest.raises(TypeError):
            InstallationManifest()  # type: ignore[call-arg]


class TestStrictReading:
    """`to_dict` writes every key, so `from_dict` accepts exactly that shape."""

    def _dict(self) -> dict:
        return _manifest(PreparationStatus.SUCCESS).to_dict()

    @pytest.mark.parametrize("value", [[], "manifest", None, 1])
    def test_rejects_a_top_level_that_is_not_an_object(self, value):
        with pytest.raises(ManifestError, match="manifest must be a JSON object"):
            InstallationManifest.from_dict(value)

    @pytest.mark.parametrize("version", [None, "v0", "v2alpha1"])
    def test_rejects_other_schema_versions(self, version):
        d = self._dict()
        d["schema_version"] = version

        with pytest.raises(ManifestError, match="unsupported manifest schema_version"):
            InstallationManifest.from_dict(d)

    def test_reports_missing_and_unknown_keys_together(self):
        d = self._dict()
        del d["schema_version"]
        del d["status"]
        d["stauts"] = "success"

        with pytest.raises(
            ManifestError,
            match=r"^manifest is missing schema_version, status and has unknown keys stauts$",
        ):
            InstallationManifest.from_dict(d)

    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            ("sdk_arms", "", "sdk_arms must be a list, not ''"),
            ("sdk_arms", None, "sdk_arms must be a list, not None"),
            ("sdk_arms", ["main"], r"sdk_arms\[0\] must be an object, not 'main'"),
            ("status_message", None, "status_message must be a string, not None"),
            (
                "status",
                "SUCCESS",
                "status must be one of success, neutral, partial, failed, not 'SUCCESS'",
            ),
            ("status", None, "status must be one of"),
            ("metadata", None, "metadata must map strings to strings"),
            ("metadata", {"sdk": 1}, "metadata must map strings to strings"),
            ("metadata", {}, "metadata.sdk is missing"),
            ("metadata", {"sdk": ""}, "metadata.sdk must not be empty"),
            ("platform", "main", "platform must be an object, not 'main'"),
            ("otdfctl", [], r"otdfctl must be an object, not \[\]"),
        ],
    )
    def test_rejects_mistyped_fields(self, field, value, error):
        d = self._dict()
        d[field] = value

        with pytest.raises(ManifestError, match=f"^{error}"):
            InstallationManifest.from_dict(d)

    def test_names_the_path_to_a_bad_arm_field(self):
        d = self._dict()
        d["sdk_arms"][1]["commit_sha"] = 5

        with pytest.raises(
            ManifestError, match=r"^sdk_arms\[1\]\.commit_sha must be a string or null, not 5$"
        ):
            InstallationManifest.from_dict(d)

    def test_names_the_path_to_a_bad_pin_field(self):
        d = self._dict()
        d["platform"] = _identity("main", sha("main")).to_dict()
        d["platform"]["commit_sha"] = "abc1234"

        with pytest.raises(ManifestError, match=r"^platform\.commit_sha must be a full"):
            InstallationManifest.from_dict(d)

    def test_read_names_the_file(self, tmp_path: Path):
        path = tmp_path / "m.json"
        d = self._dict()
        d["status"] = "SUCCESS"
        path.write_text(json.dumps(d))

        with pytest.raises(
            ManifestError, match=f"^{re.escape(str(path))}: status must be one of"
        ) as exc:
            InstallationManifest.read(path)

        assert isinstance(exc.value.__cause__, ManifestError)

    def test_read_turns_bad_json_into_a_manifest_error(self, tmp_path: Path):
        path = tmp_path / "m.json"
        path.write_text("{not json")

        with pytest.raises(ManifestError, match=f"^{re.escape(str(path))}: ") as exc:
            InstallationManifest.read(path)

        assert isinstance(exc.value.__cause__, ValueError)


class TestStatusAgreesWithContent:
    """Checked when reading only: a writer must always be able to record an abort."""

    def _reject(self, manifest: InstallationManifest, error: str) -> None:
        with pytest.raises(ManifestError, match=error):
            InstallationManifest.from_dict(manifest.to_dict())

    def test_neutral_needs_two_arms(self):
        manifest = _manifest(PreparationStatus.NEUTRAL)
        del manifest.sdk_arms[1]

        self._reject(manifest, "status neutral needs at least two sdk_arms")

    def test_neutral_arms_are_not_installed(self):
        manifest = _manifest(PreparationStatus.NEUTRAL)
        manifest.sdk_arms[1] = _identity("main", sha("one"))

        self._reject(manifest, "each with a null installed_path")

    def test_success_needs_an_arm(self):
        manifest = _manifest(PreparationStatus.SUCCESS)
        manifest.sdk_arms.clear()

        self._reject(manifest, "status success needs at least one sdk_arm")

    def test_success_arms_are_all_installed(self):
        manifest = _manifest(PreparationStatus.SUCCESS)
        manifest.sdk_arms[1] = _identity("main", None, installed=False)

        self._reject(manifest, "each with an installed_path")

    @pytest.mark.parametrize(
        "status",
        [PreparationStatus.NEUTRAL, PreparationStatus.PARTIAL, PreparationStatus.FAILED],
    )
    def test_anything_but_success_says_why(self, status):
        self._reject(_manifest(status, message=""), f"status {status.value} needs a status_message")

    def test_construction_and_write_do_not_check(self, tmp_path: Path):
        """`install benchmark` writes on every exit path; refusing one would lose the record."""
        InstallationManifest(status=PreparationStatus.SUCCESS).write(tmp_path / "m.json")


class TestResolvedArtifact:
    def test_installation_method_release(self):
        assert _resolved("v0.29.0", sha("v0.29.0"), release=True).installation_method == "release"

    def test_installation_method_source(self):
        assert _resolved("main", sha("main")).installation_method == "source"


class TestDistSlugFor:
    """The dist directory an artifact will occupy, and who decides it."""

    def test_source_build_slug_comes_from_the_expanded_alias_not_the_tag(self):
        """`resolve` reports `pr:123` as the tag `pull-123`; `cmd_tip` builds the expanded ref."""
        assert dist_slug_for(_resolved("pr:123", sha("pr"), tag="pull-123")) == (
            "refs--pull--123--head"
        )

    def test_release_slug_comes_from_the_resolved_tag_not_the_alias(self):
        """`latest` moves; the tag it resolved to does not. npm's bare tag gets a `v`."""
        latest = _resolved("latest", None, tag="0.4.0", release=True)

        assert dist_slug_for(latest) == "v0.4.0"

    def test_an_alias_and_the_release_it_names_are_one_build(self):
        """Even with no commit to compare: they share the directory the tag names."""
        latest = _resolved("latest", None, tag="0.4.0", release=True)
        pinned = _resolved("v0.4.0", None, tag="0.4.0", release=True)

        assert is_neutral_preparation([latest, pinned])


class TestCheckCollision:
    A = "a" * 40
    B = "b" * 40

    def test_no_collision(self):
        resolved = [
            _resolved("v0.29.0", self.A, release=True),
            _resolved("main", self.B),
        ]
        assert check_collision(resolved) is None

    def test_collision_detected(self):
        resolved = [
            _resolved("v0.29.0", self.A, release=True),
            # same tag, different alias
            _resolved("otdfctl/v0.29.0", self.B, tag="v0.29.0", release=True),
        ]
        error = check_collision(resolved)
        assert error is not None
        assert "Colliding installed paths" in error
        assert "v0.29.0: v0.29.0 at aaaaaaaa; otdfctl/v0.29.0 at bbbbbbbb" in error

    @pytest.mark.parametrize(
        ("first", "second"),
        [("main", "main"), ("sdk/feature", "feature"), ("Feature", "feature")],
    )
    def test_one_directory_at_one_commit_is_one_build_not_a_collision(self, first, second):
        assert check_collision([_resolved(first, self.A), _resolved(second, self.A)]) is None

    def test_namespaced_and_plain_branches_at_different_commits_collide(self):
        """js `sdk/feature` and `feature` both build into `dist/feature`."""
        error = check_collision([_resolved("sdk/feature", self.A), _resolved("feature", self.B)])

        assert error is not None
        assert "feature: sdk/feature at aaaaaaaa; feature at bbbbbbbb" in error

    def test_names_that_differ_only_in_case_collide(self):
        """`Feature` and `feature` are one directory on a case-insensitive disk."""
        error = check_collision([_resolved("Feature", self.A), _resolved("feature", self.B)])

        assert error is not None
        assert "Feature / feature: Feature at aaaaaaaa; feature at bbbbbbbb" in error

    def test_an_unknown_commit_is_named_as_such(self):
        known = _resolved("v0.4.0", "abcdef12" + "3" * 32, release=True)

        error = check_collision([known, _npm_only_release("0.4.0")])

        assert error is not None
        assert "v0.4.0: 0.4.0 at an unknown commit; v0.4.0 at abcdef12" in error


class TestIsNeutralPreparation:
    def test_neutral_same_commit(self):
        resolved = [
            _resolved("v0.29.0", sha("same"), release=True),
            _resolved("main", sha("same")),
        ]
        assert is_neutral_preparation(resolved)

    def test_one_ref_named_twice_is_neutral(self):
        assert is_neutral_preparation(
            [_resolved("main", sha("main")), _resolved("main", sha("main"))]
        )

    def test_not_neutral_different_commits(self):
        resolved = [
            _resolved("v0.29.0", sha("a"), release=True),
            _resolved("main", sha("b")),
        ]
        assert not is_neutral_preparation(resolved)

    def test_not_neutral_when_only_some_arms_share_a_commit(self):
        resolved = [
            _resolved("v0.38.0", sha("aaa"), release=True),
            _resolved("main", sha("aaa")),
            _resolved("pr:123", sha("bbb")),
        ]
        assert not is_neutral_preparation(resolved)

    def test_not_neutral_single_artifact(self):
        assert not is_neutral_preparation([_resolved("main", sha("main"))])

    def test_not_neutral_empty(self):
        assert not is_neutral_preparation([])

    def test_releases_with_unknown_commits_are_not_one_build(self):
        """Two npm-only releases share a missing commit, not a build.

        Compared by commit alone, `v0.3.0 v0.4.0` would be NEUTRAL: nothing
        built, exit 0, and a benchmark that measured nothing.
        """
        assert not is_neutral_preparation(
            [_npm_only_release("v0.3.0"), _npm_only_release("v0.4.0")]
        )

    def test_one_release_with_an_unknown_commit_asked_for_twice_is_neutral(self):
        assert is_neutral_preparation([_npm_only_release("v0.4.0"), _npm_only_release("0.4.0")])


class TestRepeatedBuilds:
    def test_arms_at_one_commit_are_grouped(self):
        arms = [
            _identity("v0.38.0", sha("aaa")),
            _identity("main", sha("aaa")),
            _identity("pr:123", sha("bbb")),
        ]

        assert repeated_builds(arms) == [["v0.38.0", "main"]]

    def test_distinct_builds_are_not(self):
        assert repeated_builds([_identity("v0.38.0", sha("a")), _identity("main", sha("b"))]) == []

    def test_unknown_commits_group_by_directory(self):
        arms = [
            _identity("v0.3.0", None),
            _identity("v0.4.0", None),
            _identity("0.4.0", None, tag="v0.4.0"),
        ]

        assert repeated_builds(arms) == [["v0.4.0", "0.4.0"]]

    def test_directories_that_differ_only_in_case_are_one(self):
        arms = [_identity("Feature", None), _identity("feature", None)]

        assert repeated_builds(arms) == [["Feature", "feature"]]
