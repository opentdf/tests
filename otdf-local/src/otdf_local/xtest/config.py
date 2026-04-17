"""Pydantic models for xtest configuration."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from ruamel.yaml import YAML

_yaml = YAML()
_yaml.default_flow_style = False
_yaml.width = 120


class ResolvedVersion(BaseModel):
    """A resolved SDK version, mirroring otdf-sdk-mgr ResolveResult."""

    sdk: str
    tag: str
    sha: str = ""
    alias: str = ""
    head: bool = False
    release: str = ""
    source: str = ""
    env: str = ""
    err: str = ""


class TestPhase(BaseModel):
    """A test phase definition."""

    name: str
    description: str = ""
    test_files: list[str] = Field(default_factory=list)
    pytest_args: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    skip_on_dispatch: bool = False
    env: dict[str, str] = Field(default_factory=dict)


class Features(BaseModel):
    """Detected platform features relevant to test execution."""

    ec_tdf: bool = True
    key_management: bool = False
    multikas: bool = True


class XtestInputs(BaseModel):
    """Original input refs that were resolved."""

    platform_ref: str = "main"
    go_ref: str = "main"
    js_ref: str = "main"
    java_ref: str = "main"
    focus_sdk: str = "all"
    otdfctl_source: str = "auto"


class XtestConfig(BaseModel):
    """Complete xtest configuration for a single test run."""

    version: str = "1"
    inputs: XtestInputs = Field(default_factory=XtestInputs)
    resolved: dict[str, list[ResolvedVersion]] = Field(default_factory=dict)
    platform_tag: str = "main"
    encrypt_sdk: str = "go"
    features: Features = Field(default_factory=Features)
    phases: list[TestPhase] = Field(default_factory=lambda: list(DEFAULT_PHASES))

    def to_yaml(self) -> str:
        """Serialize to YAML string."""
        data = self._to_dict()
        buf = io.StringIO()
        _yaml.dump(data, buf)
        return buf.getvalue()

    def to_yaml_file(self, path: Path) -> None:
        """Write config to a YAML file."""
        data = self._to_dict()
        with open(path, "w") as f:
            _yaml.dump(data, f)

    def _to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict suitable for YAML serialization."""
        data: dict[str, Any] = {
            "version": self.version,
            "inputs": _strip_defaults(self.inputs.model_dump(), XtestInputs()),
            "resolved": {},
            "platform-tag": self.platform_tag,
            "encrypt-sdk": self.encrypt_sdk,
            "features": _strip_defaults(self.features.model_dump(), Features()),
            "phases": [],
        }
        for sdk, versions in self.resolved.items():
            data["resolved"][sdk] = [_strip_empty(v.model_dump()) for v in versions]
        for phase in self.phases:
            p: dict[str, Any] = {"name": phase.name}
            if phase.description:
                p["description"] = phase.description
            if phase.test_files:
                p["test-files"] = phase.test_files
            if phase.pytest_args:
                p["pytest-args"] = phase.pytest_args
            if phase.requires:
                p["requires"] = phase.requires
            if phase.skip_on_dispatch:
                p["skip-on-dispatch"] = True
            if phase.env:
                p["env"] = phase.env
            data["phases"].append(p)
        return data

    @classmethod
    def from_yaml(cls, source: str | Path) -> XtestConfig:
        """Parse config from a YAML string or file path."""
        if isinstance(source, Path):
            with open(source) as f:
                data = _yaml.load(f)
        else:
            data = _yaml.load(source)
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> XtestConfig:
        """Build config from a parsed YAML dict."""
        inputs_data = data.get("inputs", {})
        inputs = XtestInputs(
            platform_ref=inputs_data.get("platform-ref", "main"),
            go_ref=inputs_data.get("go-ref", "main"),
            js_ref=inputs_data.get("js-ref", "main"),
            java_ref=inputs_data.get("java-ref", "main"),
            focus_sdk=inputs_data.get("focus-sdk", "all"),
            otdfctl_source=inputs_data.get("otdfctl-source", "auto"),
        )

        resolved: dict[str, list[ResolvedVersion]] = {}
        for sdk, versions in data.get("resolved", {}).items():
            resolved[sdk] = [ResolvedVersion(**v) for v in versions]

        features_data = data.get("features", {})
        features = Features(
            ec_tdf=features_data.get("ec-tdf", True),
            key_management=features_data.get("key-management", False),
            multikas=features_data.get("multikas", True),
        )

        phases = []
        for p in data.get("phases", []):
            phases.append(
                TestPhase(
                    name=p["name"],
                    description=p.get("description", ""),
                    test_files=p.get("test-files", []),
                    pytest_args=p.get("pytest-args", []),
                    requires=p.get("requires", []),
                    skip_on_dispatch=p.get("skip-on-dispatch", False),
                    env=p.get("env", {}),
                )
            )

        return cls(
            version=data.get("version", "1"),
            inputs=inputs,
            resolved=resolved,
            platform_tag=data.get("platform-tag", "main"),
            encrypt_sdk=data.get("encrypt-sdk", "go"),
            features=features,
            phases=phases if phases else list(DEFAULT_PHASES),
        )

    def check_phase_requirements(self, phase: TestPhase) -> bool:
        """Check if a phase's requirements are met by current features."""
        for req in phase.requires:
            if req == "multikas" and not self.features.multikas:
                return False
            if req == "key-management" and not self.features.key_management:
                return False
            if req == "ec-tdf" and not self.features.ec_tdf:
                return False
        return True


def _strip_empty(d: dict[str, Any]) -> dict[str, Any]:
    """Remove keys with empty/falsy values from a dict."""
    return {k: v for k, v in d.items() if v}


def _to_yaml_keys(d: dict[str, Any]) -> dict[str, Any]:
    """Convert Python snake_case keys to YAML kebab-case keys."""
    return {k.replace("_", "-"): v for k, v in d.items()}


def _strip_defaults(d: dict[str, Any], defaults: BaseModel) -> dict[str, Any]:
    """Remove keys that match the default model values, and convert to kebab-case."""
    default_dict = defaults.model_dump()
    return _to_yaml_keys({k: v for k, v in d.items() if v != default_dict.get(k)})


# Default test phases matching what xtest.yml runs
DEFAULT_PHASES: list[TestPhase] = [
    TestPhase(
        name="helpers",
        description="Validate xtest helper library",
        test_files=["test_self.py", "test_audit_logs.py"],
        skip_on_dispatch=True,
    ),
    TestPhase(
        name="legacy",
        description="Legacy decryption tests",
        test_files=["test_legacy.py"],
        pytest_args=["-n", "auto", "--dist", "worksteal"],
    ),
    TestPhase(
        name="standard",
        description="Standard TDF and policy tests",
        test_files=["test_tdfs.py", "test_policytypes.py"],
        pytest_args=["-n", "auto", "--dist", "loadscope"],
    ),
    TestPhase(
        name="abac",
        description="Attribute-based access control tests",
        test_files=["test_abac.py"],
        pytest_args=[
            "-n",
            "auto",
            "--dist",
            "loadscope",
            "--audit-log-dir",
            "test-results/audit-logs",
        ],
        requires=["multikas"],
    ),
]
