"""Unit tests for reading the benchmark installation manifest.

The manifest is written by `otdf-sdk-mgr install benchmark` and is the only
record of which commit each measured arm is. These tests pin the shape xtest
reads, and that a manifest it cannot fully read is refused rather than half
understood.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from perf import installation


def arm(alias: str, tag: str, sha: str | None) -> dict[str, object]:
    return {
        "requested_alias": alias,
        "repository": "https://github.com/opentdf/platform.git",
        "commit_sha": sha,
        "installed_tag": tag,
        "installed_path": f"/somewhere/sdk/go/dist/{tag}",
        "installation_method": "source",
        "build_settings": {},
    }


def manifest(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": "v1alpha1",
        "platform": None,
        "otdfctl": arm("v0.30.0", "v0.30.0", "c" * 40),
        "sdk_arms": [
            arm("v0.29.0", "v0.29.0", "a" * 40),
            arm("main", "main", "b" * 40),
            arm("my/branch", "my--branch", "d" * 40),
        ],
        "status": "success",
        "status_message": "",
        "metadata": {"sdk": "go"},
    }
    return base | overrides


def write(tmp_path: Path, doc: dict[str, object]) -> Path:
    path = tmp_path / "benchmark.installed.json"
    path.write_text(json.dumps(doc))
    return path


class TestRead:
    def test_arms_keep_request_order_and_map_to_dist_tags(self, tmp_path: Path):
        got = installation.read(write(tmp_path, manifest()))
        assert got.usable
        assert got.arm_specs() == ("go@v0.29.0", "go@main", "go@my--branch")
        assert got.arm_for_tag("main") is not None
        assert got.arm_for_tag("main").commit_sha == "b" * 40  # pyright: ignore[reportOptionalMemberAccess]

    def test_provenance_omits_machine_specific_paths(self, tmp_path: Path):
        doc = installation.read(write(tmp_path, manifest())).to_dict()
        assert "installed_path" not in json.dumps(doc)
        assert doc["otdfctl"]["installed_tag"] == "v0.30.0"  # pyright: ignore[reportIndexIssue]

    def test_an_unknown_commit_stays_unknown(self, tmp_path: Path):
        # A js release found on npm but not in git has no commit to record.
        doc = manifest(
            sdk_arms=[arm("v0.4.0", "v0.4.0", None), arm("main", "main", "b" * 40)]
        )
        got = installation.read(write(tmp_path, doc))
        assert got.arms[0].commit_sha is None
        assert got.to_dict()["arms"][0]["commit_sha"] is None  # pyright: ignore[reportIndexIssue]

    def test_neutral_is_recognized_and_not_usable(self, tmp_path: Path):
        got = installation.read(
            write(tmp_path, manifest(status="neutral", status_message="same commit"))
        )
        assert got.neutral
        assert not got.usable

    @pytest.mark.parametrize(
        ("overrides", "match"),
        [
            ({"schema_version": "v2"}, "schema"),
            ({"metadata": {}}, "metadata.sdk"),
            ({"sdk_arms": [{"requested_alias": "main"}]}, "missing"),
            ({"sdk_arms": "main"}, "not a list"),
        ],
    )
    def test_an_unusable_manifest_is_refused(
        self, tmp_path: Path, overrides: dict[str, object], match: str
    ):
        with pytest.raises(installation.ManifestError, match=match):
            installation.read(write(tmp_path, manifest(**overrides)))

    def test_invalid_json_is_refused(self, tmp_path: Path):
        path = tmp_path / "m.json"
        path.write_text("{not json")
        with pytest.raises(installation.ManifestError, match="not valid JSON"):
            installation.read(path)


class TestFromEnv:
    def test_unset_means_not_prepared(self):
        assert installation.from_env({}) is None

    def test_set_but_missing_is_an_error_not_a_fallback(self, tmp_path: Path):
        with pytest.raises(installation.ManifestError, match="cannot read"):
            installation.from_env(
                {installation.MANIFEST_ENV: str(tmp_path / "absent.json")}
            )
