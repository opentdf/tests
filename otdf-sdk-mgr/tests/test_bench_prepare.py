"""Behavioral checks for benchmark installation without building SDKs."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from otdf_sdk_mgr import bench_prepare
from otdf_sdk_mgr.manifest import (
    ArtifactIdentity,
    InstallationManifest,
    PreparationStatus,
    ResolvedArtifact,
)


def arm(alias: str, sha: str | None, *, release: bool = False) -> ResolvedArtifact:
    return ResolvedArtifact(
        requested_alias=alias,
        repository="https://github.com/opentdf/platform.git",
        commit_sha=sha,
        tag=alias,
        is_head=not release,
        is_release=release,
    )


def installed(artifact: ResolvedArtifact) -> ArtifactIdentity:
    return ArtifactIdentity(
        requested_alias=artifact.requested_alias,
        repository=artifact.repository,
        commit_sha=artifact.commit_sha,
        installed_tag=artifact.tag,
        installed_path=f"/sdk/dist/{artifact.tag}",
        installation_method=artifact.installation_method,
    )


def prepare(tmp_path: Path, *aliases: str, **kwargs) -> InstallationManifest:
    path = tmp_path / "benchmark.installed.json"
    result = bench_prepare.prepare_benchmark("go", list(aliases), manifest_path=path, **kwargs)
    assert InstallationManifest.read(path) == result
    return result


@pytest.fixture
def two_arms(monkeypatch):
    arms = [arm("v1.0.0", "a" * 40, release=True), arm("main", "b" * 40)]
    monkeypatch.setattr(bench_prepare, "resolve_ordered", lambda sdk, refs: (arms, None))
    install = Mock(side_effect=lambda sdk, artifact: installed(artifact))
    monkeypatch.setattr(bench_prepare, "install_artifact", install)
    return arms, install


def test_resolves_ordered_refs_and_keeps_the_requested_alias(monkeypatch):
    def resolve(sdk, ref, infix=None):
        return {"sha": "a" * 40, "tag": "pull-12", "head": True}

    resolver = Mock(side_effect=resolve)
    monkeypatch.setattr(bench_prepare, "resolve", resolver)

    resolved, error = bench_prepare.resolve_ordered("go", ["pr:12", "main"])

    assert error is None
    assert [item.requested_alias for item in resolved] == ["pr:12", "main"]
    assert resolver.call_args_list[0].args[1] == "refs/pull/12/head"


@pytest.mark.parametrize("sdk", ["go", "java", "js"])
def test_resolves_releases_with_the_sdk_tag_namespace(monkeypatch, sdk):
    resolver = Mock(return_value={"sha": "a" * 40, "tag": "v1.0.0", "release": "v1.0.0"})
    monkeypatch.setattr(bench_prepare, "resolve", resolver)

    resolved, error = bench_prepare.resolve_ordered(sdk, ["v1.0.0"])

    assert error is None
    assert resolved[0].is_release
    assert resolver.call_args.kwargs["infix"] == ("sdk" if sdk == "js" else None)


@pytest.mark.parametrize(
    ("sdk", "refs", "response", "message"),
    [
        ("platform", ["main"], None, "Unknown SDK"),
        ("go", [], None, "No refs"),
        ("go", ["bad"], {"err": "missing"}, "missing"),
        ("go", ["abc1234"], {"sha": "abc1234", "tag": "abc1234"}, "full commit SHA"),
    ],
)
def test_resolution_rejects_invalid_requests(monkeypatch, sdk, refs, response, message):
    if response is not None:
        monkeypatch.setattr(bench_prepare, "resolve", lambda *args, **kwargs: response)
    resolved, error = bench_prepare.resolve_ordered(sdk, refs)
    assert resolved == []
    assert message in error


def test_same_build_is_neutral_and_installs_nothing(monkeypatch, tmp_path):
    arms = [arm("v1.0.0", "a" * 40, release=True), arm("main", "a" * 40)]
    monkeypatch.setattr(bench_prepare, "resolve_ordered", lambda sdk, refs: (arms, None))
    install = Mock()
    monkeypatch.setattr(bench_prepare, "install_artifact", install)

    result = prepare(tmp_path, "v1.0.0", "main")

    assert result.status == PreparationStatus.NEUTRAL
    assert [item.requested_alias for item in result.sdk_arms] == ["v1.0.0", "main"]
    assert all(item.installed_path is None for item in result.sdk_arms)
    install.assert_not_called()


def test_dist_collision_stops_before_install(monkeypatch, tmp_path):
    # These distinct refs both install to dist/feature.
    arms = [arm("sdk/feature", "a" * 40), arm("feature", "b" * 40)]
    monkeypatch.setattr(bench_prepare, "resolve_ordered", lambda sdk, refs: (arms, None))
    install = Mock()
    monkeypatch.setattr(bench_prepare, "install_artifact", install)

    result = prepare(tmp_path, "sdk/feature", "feature")

    assert result.status == PreparationStatus.FAILED
    assert "Colliding installed paths" in result.status_message
    install.assert_not_called()


def test_npm_only_releases_use_the_version_to_identify_a_build(monkeypatch, tmp_path):
    def resolve(sdk, ref, infix=None):
        version = "0.4.0" if ref == "latest" else ref.removeprefix("v")
        return {"sha": "", "tag": version, "release": version}

    monkeypatch.setattr(bench_prepare, "resolve", resolve)
    monkeypatch.setattr(bench_prepare, "install_artifact", lambda sdk, item: installed(item))

    same = bench_prepare.prepare_benchmark(
        "js", ["latest", "v0.4.0"], manifest_path=tmp_path / "same.json"
    )
    different = bench_prepare.prepare_benchmark(
        "js", ["v0.4.0", "v0.5.0"], manifest_path=tmp_path / "different.json"
    )

    assert same.status == PreparationStatus.NEUTRAL
    assert different.status == PreparationStatus.SUCCESS


def test_installs_in_request_order_and_records_pins(monkeypatch, tmp_path, two_arms):
    arms, install = two_arms
    pin = arm("pin", "c" * 40)
    monkeypatch.setattr(
        bench_prepare,
        "resolve_ordered",
        lambda sdk, refs: ([pin], None) if refs == ["pin"] else (arms, None),
    )
    monkeypatch.setattr(
        bench_prepare, "_install_platform", lambda ref: installed(arm(ref, "d" * 40))
    )

    result = prepare(tmp_path, "v1.0.0", "main", platform_ref="platform-ref", otdfctl_ref="pin")

    assert result.status == PreparationStatus.SUCCESS
    assert [item.requested_alias for item in result.sdk_arms] == ["v1.0.0", "main"]
    assert result.platform is not None
    assert result.otdfctl is not None
    assert result.platform.requested_alias == "platform-ref"
    assert result.otdfctl.requested_alias == "pin"
    assert [call.args[1].requested_alias for call in install.call_args_list] == [
        "v1.0.0",
        "main",
        "pin",
    ]


def test_otdfctl_pin_cannot_overwrite_an_arm(monkeypatch, tmp_path, two_arms):
    arms, install = two_arms
    pin = arm("main", "c" * 40)
    monkeypatch.setattr(
        bench_prepare,
        "resolve_ordered",
        lambda sdk, refs: ([pin], None) if refs == ["pin"] else (arms, None),
    )

    result = prepare(tmp_path, "v1.0.0", "main", otdfctl_ref="pin")

    assert result.status == PreparationStatus.FAILED
    assert "Colliding installed paths" in result.status_message
    install.assert_not_called()


def test_failed_arm_keeps_prior_installs_in_manifest(monkeypatch, tmp_path, two_arms):
    arms, install = two_arms
    install.side_effect = [installed(arms[0]), bench_prepare.BenchPrepareError("build failed")]

    result = prepare(tmp_path, "v1.0.0", "main")

    assert result.status == PreparationStatus.PARTIAL
    assert [item.requested_alias for item in result.sdk_arms] == ["v1.0.0"]
    assert "build failed" in result.status_message


def test_bad_pin_fails_before_building_arms(monkeypatch, tmp_path, two_arms):
    arms, install = two_arms
    monkeypatch.setattr(
        bench_prepare,
        "resolve_ordered",
        lambda sdk, refs: ([], "unknown pin") if refs == ["bad"] else (arms, None),
    )

    result = prepare(tmp_path, "v1.0.0", "main", otdfctl_ref="bad")

    assert result.status == PreparationStatus.FAILED
    assert "unknown pin" in result.status_message
    install.assert_not_called()


def test_interrupt_records_partial_run(monkeypatch, tmp_path, two_arms):
    arms, install = two_arms
    path = tmp_path / "benchmark.installed.json"
    InstallationManifest(status=PreparationStatus.SUCCESS).write(path)
    install.side_effect = [installed(arms[0]), KeyboardInterrupt()]

    with pytest.raises(KeyboardInterrupt):
        bench_prepare.prepare_benchmark("go", ["v1.0.0", "main"], manifest_path=path)

    result = InstallationManifest.read(path)
    assert result.status == PreparationStatus.PARTIAL
    assert [item.requested_alias for item in result.sdk_arms] == ["v1.0.0"]


def test_unwritable_manifest_fails_before_resolving(monkeypatch, tmp_path):
    (tmp_path / "file").write_text("")
    resolve = Mock()
    monkeypatch.setattr(bench_prepare, "resolve_ordered", resolve)

    with pytest.raises(bench_prepare.BenchPrepareError, match="cannot write the manifest"):
        bench_prepare.prepare_benchmark("go", ["main"], manifest_path=tmp_path / "file" / "m.json")

    resolve.assert_not_called()


def test_release_uses_install_release(monkeypatch, tmp_path):
    monkeypatch.setattr(bench_prepare, "get_sdk_dirs", lambda: {"js": tmp_path / "js"})
    release = Mock(return_value=tmp_path / "js" / "dist" / "v1.0.0")
    monkeypatch.setattr(bench_prepare, "install_release", release)

    result = bench_prepare.install_artifact("js", arm("v1.0.0", "a" * 40, release=True))

    assert result.installation_method == "release"
    assert result.installed_tag == "v1.0.0"
    assert release.call_count == 1


def test_source_build_records_actual_commit_and_reuses_it(monkeypatch, tmp_path):
    sdk_dir = tmp_path / "go"
    dist = sdk_dir / "dist" / "main"
    monkeypatch.setattr(bench_prepare, "get_sdk_dirs", lambda: {"go": sdk_dir})
    monkeypatch.setattr(bench_prepare, "_built_commit", lambda sdk_dir, slug: "a" * 40)
    build = Mock(side_effect=lambda sdks, ref: dist.mkdir(parents=True))
    monkeypatch.setattr(bench_prepare, "cmd_tip", build)
    source = arm("main", "a" * 40)

    first = bench_prepare.install_artifact("go", source)
    second = bench_prepare.install_artifact("go", source)

    assert first.commit_sha == second.commit_sha == "a" * 40
    assert bench_prepare.read_dist_commit(dist) == "a" * 40
    assert build.call_count == 1


def test_stale_source_dist_is_rebuilt(monkeypatch, tmp_path):
    sdk_dir = tmp_path / "go"
    dist = sdk_dir / "dist" / "main"
    dist.mkdir(parents=True)
    (dist / ".version").write_text("sha=" + "b" * 40)
    (dist / "stale").write_text("")
    monkeypatch.setattr(bench_prepare, "get_sdk_dirs", lambda: {"go": sdk_dir})
    monkeypatch.setattr(bench_prepare, "_built_commit", lambda sdk_dir, slug: "a" * 40)
    build = Mock(side_effect=lambda sdks, ref: dist.mkdir(parents=True))
    monkeypatch.setattr(bench_prepare, "cmd_tip", build)

    bench_prepare.install_artifact("go", arm("main", "a" * 40))

    assert build.call_count == 1
    assert not (dist / "stale").exists()


def test_moved_ref_is_reported_instead_of_mislabeling_build(monkeypatch, tmp_path):
    sdk_dir = tmp_path / "go"
    dist = sdk_dir / "dist" / "main"
    monkeypatch.setattr(bench_prepare, "get_sdk_dirs", lambda: {"go": sdk_dir})
    monkeypatch.setattr(bench_prepare, "_built_commit", lambda sdk_dir, slug: "b" * 40)
    monkeypatch.setattr(bench_prepare, "cmd_tip", lambda sdks, ref: dist.mkdir(parents=True))

    with pytest.raises(bench_prepare.BenchPrepareError, match="moved during preparation"):
        bench_prepare.install_artifact("go", arm("main", "a" * 40))

    assert bench_prepare.read_dist_commit(dist) == "b" * 40
