"""Shared Pydantic models for OpenTDF scenarios and instances.

Both `otdf-sdk-mgr` and `otdf-local` import from this module so the on-disk
YAML formats (`scenarios.yaml`, `instance.yaml`) have exactly one canonical
definition.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from ruamel.yaml import YAML, YAMLError

API_VERSION = "opentdf.io/v1alpha1"

# KAS Preview Settings
#
# The `KasPin.features` dict specifies preview settings written to the generated
# opentdf.yaml as `services.kas.preview.<key>: <value>`. Available preview
# settings vary by platform version; common examples include ec_tdf_enabled,
# hybrid_tdf_enabled, and key_management.
#
# Precedence (last wins): template defaults → mode auto-enables → user features
#
# Example:
#   kas:
#     km1:
#       mode: key_management
#       features:
#         hybrid_tdf_enabled: true  # Enable ML-KEM in addition to auto-enabled features

KasMode = Literal["standard", "key_management"]
SdkName = Literal["go", "java", "js"]
# Canonical Base TDF profiles (docs/FORMATS.md). Legacy "ztdf" normalizes to tdf.
ContainerKind = Literal["tdf", "tdf-ecwrap"]

_CONTAINER_ALIASES: dict[str, ContainerKind] = {
    "tdf": "tdf",
    "base-tdf": "tdf",
    "standard-tdf": "tdf",
    "ztdf": "tdf",  # legacy OpenTDF tooling name for Base TDF ZIP
    "tdf-ecwrap": "tdf-ecwrap",
    "base-tdf-ecwrap": "tdf-ecwrap",
    "ztdf-ecwrap": "tdf-ecwrap",
}


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


class SourceRef(_StrictModel):
    ref: str = Field(description="Git tag, branch, or SHA")
    path: Path | None = Field(default=None, description="Optional local checkout path")


class PlatformPin(_StrictModel):
    """Version pin for the platform service.

    `dist` references a built binary at `xtest/platform/dist/<dist>/service`
    produced by `otdf-sdk-mgr install platform:<version>`.
    `source.ref` is a git ref to build from on demand.
    """

    dist: str | None = None
    source: SourceRef | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> PlatformPin:
        set_fields = [k for k in ("dist", "source") if getattr(self, k) is not None]
        if len(set_fields) != 1:
            raise ValueError(
                f"PlatformPin must set exactly one of dist|source (got {set_fields or 'none'})"
            )
        return self


class KasPin(_StrictModel):
    """Per-KAS-instance version + mode pin."""

    dist: str | None = None
    source: SourceRef | None = None
    mode: KasMode = "standard"
    features: dict[str, bool] = Field(
        default_factory=dict,
        description=(
            "KAS preview settings to enable. Keys are preview setting names "
            "(without the 'services.kas.preview.' prefix); values are booleans. "
            "Available settings depend on the platform version and may include "
            "experimental features in PRs. User-specified features override "
            "mode-based defaults."
        ),
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> KasPin:
        set_fields = [k for k in ("dist", "source") if getattr(self, k) is not None]
        if len(set_fields) != 1:
            raise ValueError(
                f"KasPin must set exactly one of dist|source (got {set_fields or 'none'})"
            )
        return self


class ScenarioSdk(_StrictModel):
    """One ordered SDK selection within a scenario role."""

    sdk: SdkName
    version: str
    source: str | None = Field(
        default=None,
        description='For Go: "platform" to use the monorepo module path',
    )

    def install_key(self) -> tuple[SdkName, str, str | None]:
        return (self.sdk, self.version, self.source)


class PortsConfig(_StrictModel):
    base: int = Field(default=8080, ge=1024, le=60000)


class Metadata(_StrictModel):
    name: str | None = None
    id: str | None = None
    title: str | None = None
    created: date | None = None


class Fixtures(_StrictModel):
    attributes: Path | None = None
    policy: Path | None = None


class Instance(_StrictModel):
    """Standalone instance definition (one platform + N KAS).

    Persisted to `tests/instances/<name>/instance.yaml`. Also embedded inside
    Scenario to keep the "describe a bug-repro environment" entry point a
    single file.
    """

    apiVersion: Literal["opentdf.io/v1alpha1"] = API_VERSION
    kind: Literal["Instance"] = "Instance"
    metadata: Metadata = Field(default_factory=Metadata)
    platform: PlatformPin
    ports: PortsConfig = Field(default_factory=PortsConfig)
    kas: dict[str, KasPin] = Field(default_factory=dict)
    features: dict[str, bool] = Field(
        default_factory=dict,
        description=(
            "Reserved for future use. Instance-level feature defaults are not "
            "currently implemented. Use per-KAS features in the kas dict instead."
        ),
    )
    fixtures: Fixtures = Field(default_factory=Fixtures)


class ScenarioSdks(_StrictModel):
    """Encrypt/decrypt split mirrors xtest's --sdks-encrypt/--sdks-decrypt.

    Selections are ordered to preserve the eventual argv order, and are
    de-duplicated within each role by (sdk, version, source).
    """

    encrypt: list[ScenarioSdk] = Field(default_factory=list)
    decrypt: list[ScenarioSdk] = Field(default_factory=list)

    @model_validator(mode="after")
    def _dedupe_per_role(self) -> ScenarioSdks:
        for role in ("encrypt", "decrypt"):
            seen: set[tuple[SdkName, str, str | None]] = set()
            duplicates = []
            for entry in getattr(self, role):
                key = entry.install_key()
                if key in seen:
                    duplicates.append(key)
                seen.add(key)
            if duplicates:
                raise ValueError(
                    f"ScenarioSdks.{role} contains duplicate sdk/version entries: {duplicates}"
                )
        return self

    def union(self) -> list[ScenarioSdk]:
        """Return the ordered union of encrypt+decrypt selections."""
        out: list[ScenarioSdk] = []
        seen: set[tuple[SdkName, str, str | None]] = set()
        for entry in [*self.encrypt, *self.decrypt]:
            key = entry.install_key()
            if key in seen:
                continue
            seen.add(key)
            out.append(entry)
        return out


class Suite(_StrictModel):
    """Pytest selection + flags."""

    targets: list[str] = Field(
        default_factory=list,
        description="Positional pytest targets, e.g. test files or path::node ids",
    )
    kexpr: str | None = Field(default=None, description="Forwarded to pytest -k")
    containers: list[ContainerKind] = Field(
        default_factory=list,
        description=(
            "Format profiles for --containers: tdf (Base TDF), tdf-ecwrap. "
            "Legacy aliases ztdf / ztdf-ecwrap normalize to tdf / tdf-ecwrap."
        ),
    )
    markers: str | None = Field(default=None, description="Forwarded to -m")
    extra_args: list[str] = Field(default_factory=list)

    @field_validator("containers", mode="before")
    @classmethod
    def _normalize_containers(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        out: list[str] = []
        for item in value:
            key = str(item).strip().lower()
            if key in _CONTAINER_ALIASES:
                out.append(_CONTAINER_ALIASES[key])
            else:
                out.append(str(item))
        return out


class Scenario(_StrictModel):
    """Top-level scenarios.yaml model.

    Composes an Instance with SDK pins and a pytest Suite selection.
    """

    apiVersion: Literal["opentdf.io/v1alpha1"] = API_VERSION
    kind: Literal["Scenario"] = "Scenario"
    metadata: Metadata = Field(default_factory=Metadata)
    instance: Annotated[Instance, Field(description="Inline instance definition")]
    sdks: ScenarioSdks = Field(default_factory=ScenarioSdks)
    suite: Suite
    expected: str | None = None
    actual: str | None = None


def _yaml() -> YAML:
    return YAML(typ="safe")


def load_yaml_mapping(path: str | Path) -> dict[str, object]:
    """Parse `path` as YAML and assert the top-level is a mapping."""
    p = Path(path)
    raw = _yaml().load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{p}: top-level YAML must be a mapping, got {type(raw).__name__}")
    return raw


def load_scenario(path: str | Path) -> Scenario:
    """Parse and validate a scenarios.yaml file."""
    return Scenario.model_validate(load_yaml_mapping(path))


def load_instance(path: str | Path) -> Instance:
    """Parse and validate an instance.yaml file."""
    return Instance.model_validate(load_yaml_mapping(path))


def dump_instance(instance: Instance, path: str | Path) -> None:
    """Serialize an Instance to YAML at `path`."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = instance.model_dump(mode="json", exclude_none=True)
    y = _yaml()
    with p.open("w", encoding="utf-8") as f:
        y.dump(data, f)


def installed_json_for(scenario_path: str | Path) -> Path:
    """Path to the install-record file `otdf-sdk-mgr install scenario` writes.

    Convention: alongside the scenario, with `.installed.json` swapped in for
    the file's suffix. e.g. `xtest/scenarios/x.yaml` →
    `xtest/scenarios/x.installed.json`.
    """
    p = Path(scenario_path)
    return p.with_suffix(".installed.json")


def scenario_to_pytest_sdks(
    scenario: Scenario,
    installed_json_path: str | Path,
) -> dict[str, list[str]]:
    """Turn a Scenario's encrypt/decrypt SDK pins into xtest `--sdks-*` tokens.

    After PR #446, xtest's `--sdks`, `--sdks-encrypt`, and `--sdks-decrypt`
    accept whitespace-separated `sdk@version` specifiers where `version`
    must match a directory name under `xtest/sdk/<lang>/dist/`. Scenario
    version fields may be aliases (`lts`, `tip`) that only resolve after
    `otdf-sdk-mgr install scenario` writes a sibling `.installed.json`
    recording the dist paths actually laid down on disk.

    Returns `{"encrypt": [...], "decrypt": [...]}` with each list containing
    `sdk@<dist-name>` tokens. Raises `FileNotFoundError` (with an actionable
    hint) when `installed.json` is missing, and `ValueError` when the
    scenario references an SDK the install record doesn't cover.
    """
    p = Path(installed_json_path)
    if not p.is_file():
        raise FileNotFoundError(
            f"{p} not found. Run `otdf-sdk-mgr install scenario <scenario.yaml>` "
            "first so the dist names get resolved; scenario_to_pytest_sdks needs "
            "the installed record to translate aliases like `lts`/`tip` into the "
            "concrete `sdk@version` tokens xtest's pytest options expect."
        )
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{p}: malformed installed.json: {e}") from e
    sdk_map = data.get("sdks", {}) if isinstance(data, dict) else {}

    def token(role: str, entry: ScenarioSdk) -> str:
        role_map = sdk_map.get(role)
        if not isinstance(role_map, list):
            raise ValueError(
                f"{p}: missing install records for role '{role}'. "
                "Re-run `otdf-sdk-mgr install scenario`."
            )
        install_entry = next(
            (
                candidate
                for candidate in role_map
                if isinstance(candidate, dict)
                and candidate.get("sdk") == entry.sdk
                and candidate.get("version") == entry.version
                and candidate.get("source") == entry.source
            ),
            None,
        )
        if not isinstance(install_entry, dict) or "path" not in install_entry:
            raise ValueError(
                f"Scenario references {role} SDK '{entry.sdk}' version '{entry.version}'"
                f"{' source ' + entry.source if entry.source else ''}, but {p} has no matching "
                "install record for it. Re-run `otdf-sdk-mgr install scenario`."
            )
        dist_name = Path(str(install_entry["path"])).name
        return f"{entry.sdk}@{dist_name}"

    return {
        "encrypt": [token("encrypt", entry) for entry in scenario.sdks.encrypt],
        "decrypt": [token("decrypt", entry) for entry in scenario.sdks.decrypt],
    }


def _main(argv: list[str] | None = None) -> int:
    """`python -m otdf_sdk_mgr.schema validate <path>` entry point."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "validate":
        print("usage: python -m otdf_sdk_mgr.schema validate <path>", file=sys.stderr)
        return 2
    path = Path(args[1])
    try:
        raw = load_yaml_mapping(path)
    except OSError as e:
        print(f"error: cannot read {path}: {e}", file=sys.stderr)
        return 1
    except YAMLError as e:
        print(f"error: invalid YAML in {path}: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    kind = raw.get("kind")
    model: type[BaseModel]
    if kind == "Scenario":
        model = Scenario
    elif kind == "Instance":
        model = Instance
    else:
        print(
            f"error: {path} has unknown kind {kind!r}; expected Scenario or Instance",
            file=sys.stderr,
        )
        return 1
    try:
        model.model_validate(raw)
    except ValidationError as e:
        print(f"invalid: {e}", file=sys.stderr)
        return 1
    print(f"ok: {path} ({kind})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
