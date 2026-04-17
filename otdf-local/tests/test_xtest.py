"""Unit tests for xtest orchestration helpers."""

from pathlib import Path

from otdf_local.xtest import (
    ResolvedVersion,
    XTestOptions,
    XTestRefs,
    XTestResolved,
    XTestRunConfig,
    _load_config,
    _resolved_otdfctl_source,
    _summary_markdown,
    _supports_multikas,
    _write_config,
)


def sample_config() -> XTestRunConfig:
    return XTestRunConfig(
        refs=XTestRefs(platform="main", go="main latest", js="main", java="main"),
        options=XTestOptions(
            encrypt_sdk="go",
            focus_sdk="all",
            otdfctl_source="auto",
            include_helper_tests=True,
        ),
        resolved=XTestResolved(
            platform=[
                ResolvedVersion(
                    sdk="platform",
                    alias="main",
                    tag="main",
                    sha="0123456789abcdef0123456789abcdef01234567",
                    head=True,
                )
            ],
            go=[
                ResolvedVersion(
                    sdk="go",
                    alias="main",
                    tag="main",
                    sha="fedcba9876543210fedcba9876543210fedcba98",
                    head=True,
                )
            ],
            js=[
                ResolvedVersion(
                    sdk="js",
                    alias="main",
                    tag="main",
                    sha="1111111111111111111111111111111111111111",
                    head=True,
                )
            ],
            java=[
                ResolvedVersion(
                    sdk="java",
                    alias="main",
                    tag="main",
                    sha="2222222222222222222222222222222222222222",
                    head=True,
                )
            ],
        ),
    )


def test_summary_markdown_contains_yaml_and_replay_command():
    config = sample_config()

    summary = _summary_markdown(config)

    assert "Local Repro" in summary
    assert "uv run --project otdf-local otdf-local xtest run --config xtest-repro.yaml" in summary
    assert "encrypt_sdk: go" in summary
    assert "platform: main" in summary


def test_config_roundtrip(tmp_path: Path):
    path = tmp_path / "xtest-repro.yaml"
    config = sample_config()

    _write_config(path, config)
    loaded = _load_config(path)

    assert loaded == config


def test_resolved_otdfctl_source_auto_prefers_embedded_checkout(tmp_path: Path):
    platform_dir = tmp_path / "platform"
    embedded = platform_dir / "otdfctl"
    embedded.mkdir(parents=True)
    (embedded / "go.mod").write_text("module github.com/opentdf/platform/otdfctl\n")

    config = sample_config()
    assert _resolved_otdfctl_source(config, platform_dir) == "platform"

    config.options.otdfctl_source = "standalone"
    assert _resolved_otdfctl_source(config, platform_dir) == "standalone"


def test_supports_multikas_semver_gate():
    assert _supports_multikas("main", "0.1.0") is True
    assert _supports_multikas("v0.5.0", "v0.5.0") is True
    assert _supports_multikas("v0.4.9", "v0.4.9") is False
