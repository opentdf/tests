"""Tests for xtest config models: serialization, parsing, requirements."""

from __future__ import annotations

from pathlib import Path

from otdf_local.xtest.config import (
    DEFAULT_PHASES,
    Features,
    ResolvedVersion,
    TestPhase,
    XtestConfig,
    XtestInputs,
)

SAMPLE_CONFIG_YAML = """\
version: '1'
inputs:
  platform-ref: main
  go-ref: v0.29.0
  focus-sdk: go
resolved:
  platform:
  - sdk: platform
    tag: main
    sha: abc1234567890
    alias: main
    head: true
  go:
  - sdk: go
    tag: v0.29.0
    sha: def5678901234
    alias: latest
    release: v0.29.0
  js:
  - sdk: js
    tag: '0.9.0'
    sha: aaa1111222233
    alias: latest
    release: sdk/0.9.0
  java:
  - sdk: java
    tag: v0.12.0
    sha: bbb2222333344
    alias: latest
    release: v0.12.0
platform-tag: main
encrypt-sdk: go
features:
  ec-tdf: true
  multikas: true
phases:
- name: legacy
  test-files:
  - test_legacy.py
  pytest-args:
  - -n
  - auto
- name: abac
  test-files:
  - test_abac.py
  requires:
  - multikas
"""


class TestXtestConfigRoundTrip:
    """Config can be serialized to YAML and parsed back identically."""

    def test_round_trip_from_objects(self):
        config = XtestConfig(
            inputs=XtestInputs(platform_ref="main", go_ref="v0.29.0", focus_sdk="go"),
            resolved={
                "platform": [
                    ResolvedVersion(
                        sdk="platform", tag="main", sha="abc123", head=True
                    ),
                ],
                "go": [
                    ResolvedVersion(
                        sdk="go", tag="v0.29.0", sha="def456", release="v0.29.0"
                    ),
                ],
            },
            platform_tag="main",
            encrypt_sdk="go",
            features=Features(ec_tdf=True, key_management=False, multikas=True),
            phases=[
                TestPhase(name="legacy", test_files=["test_legacy.py"]),
                TestPhase(
                    name="abac", test_files=["test_abac.py"], requires=["multikas"]
                ),
            ],
        )

        yaml_str = config.to_yaml()
        parsed = XtestConfig.from_yaml(yaml_str)

        assert parsed.version == config.version
        assert parsed.platform_tag == config.platform_tag
        assert parsed.encrypt_sdk == config.encrypt_sdk
        assert parsed.inputs.focus_sdk == "go"
        assert parsed.inputs.go_ref == "v0.29.0"
        assert len(parsed.resolved["platform"]) == 1
        assert parsed.resolved["platform"][0].sha == "abc123"
        assert parsed.resolved["go"][0].release == "v0.29.0"
        assert parsed.features.ec_tdf is True
        assert parsed.features.key_management is False
        assert len(parsed.phases) == 2
        assert parsed.phases[1].requires == ["multikas"]

    def test_round_trip_file(self, tmp_path: Path):
        config = XtestConfig(
            resolved={
                "go": [ResolvedVersion(sdk="go", tag="main", sha="aaa111", head=True)]
            },
        )
        out_file = tmp_path / "config.yaml"
        config.to_yaml_file(out_file)
        parsed = XtestConfig.from_yaml(out_file)
        assert parsed.resolved["go"][0].sha == "aaa111"

    def test_parse_sample_yaml(self):
        config = XtestConfig.from_yaml(SAMPLE_CONFIG_YAML)
        assert config.platform_tag == "main"
        assert config.encrypt_sdk == "go"
        assert config.inputs.go_ref == "v0.29.0"
        assert config.inputs.focus_sdk == "go"
        assert len(config.resolved["platform"]) == 1
        assert config.resolved["platform"][0].head is True
        assert config.resolved["go"][0].release == "v0.29.0"
        assert config.resolved["js"][0].tag == "0.9.0"
        assert config.features.ec_tdf is True
        assert config.features.multikas is True
        assert len(config.phases) == 2
        assert config.phases[0].name == "legacy"
        assert config.phases[1].requires == ["multikas"]


class TestDefaultPhases:
    """Default phase definitions are valid and complete."""

    def test_default_phases_exist(self):
        assert len(DEFAULT_PHASES) == 4

    def test_default_phase_names(self):
        names = [p.name for p in DEFAULT_PHASES]
        assert names == ["helpers", "legacy", "standard", "abac"]

    def test_abac_requires_multikas(self):
        abac = next(p for p in DEFAULT_PHASES if p.name == "abac")
        assert "multikas" in abac.requires

    def test_helpers_skip_on_dispatch(self):
        helpers = next(p for p in DEFAULT_PHASES if p.name == "helpers")
        assert helpers.skip_on_dispatch is True

    def test_all_phases_have_test_files(self):
        for phase in DEFAULT_PHASES:
            assert len(phase.test_files) > 0, f"Phase {phase.name} has no test files"


class TestFeatureRequirements:
    """Phase requirement checking works correctly."""

    def test_met_requirements(self):
        config = XtestConfig(features=Features(multikas=True, ec_tdf=True))
        phase = TestPhase(
            name="abac", test_files=["test_abac.py"], requires=["multikas"]
        )
        assert config.check_phase_requirements(phase) is True

    def test_unmet_requirements(self):
        config = XtestConfig(features=Features(multikas=False))
        phase = TestPhase(
            name="abac", test_files=["test_abac.py"], requires=["multikas"]
        )
        assert config.check_phase_requirements(phase) is False

    def test_no_requirements(self):
        config = XtestConfig(features=Features())
        phase = TestPhase(name="legacy", test_files=["test_legacy.py"])
        assert config.check_phase_requirements(phase) is True

    def test_key_management_requirement(self):
        config = XtestConfig(features=Features(key_management=False))
        phase = TestPhase(
            name="km", test_files=["test.py"], requires=["key-management"]
        )
        assert config.check_phase_requirements(phase) is False

        config.features.key_management = True
        assert config.check_phase_requirements(phase) is True

    def test_ec_tdf_requirement(self):
        config = XtestConfig(features=Features(ec_tdf=False))
        phase = TestPhase(name="ec", test_files=["test.py"], requires=["ec-tdf"])
        assert config.check_phase_requirements(phase) is False


class TestStripDefaults:
    """YAML output omits fields that match defaults for cleaner output."""

    def test_default_inputs_stripped(self):
        config = XtestConfig()
        yaml_str = config.to_yaml()
        # Default inputs should be stripped (empty dict or missing keys)
        parsed = XtestConfig.from_yaml(yaml_str)
        assert parsed.inputs.platform_ref == "main"
        assert parsed.inputs.focus_sdk == "all"

    def test_non_default_inputs_preserved(self):
        config = XtestConfig(
            inputs=XtestInputs(focus_sdk="go", go_ref="v1.0.0"),
        )
        yaml_str = config.to_yaml()
        assert "focus-sdk: go" in yaml_str
        assert "go-ref: v1.0.0" in yaml_str


class TestResolvedVersionErrors:
    """Error versions are preserved through serialization."""

    def test_error_version_round_trip(self):
        config = XtestConfig(
            resolved={
                "go": [ResolvedVersion(sdk="go", tag="bad-ref", err="Not found")],
            },
        )
        yaml_str = config.to_yaml()
        parsed = XtestConfig.from_yaml(yaml_str)
        assert parsed.resolved["go"][0].err == "Not found"
        assert parsed.resolved["go"][0].sha == ""
