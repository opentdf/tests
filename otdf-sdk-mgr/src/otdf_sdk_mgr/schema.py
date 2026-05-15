"""Shared Pydantic models for OpenTDF scenarios and instances.

Both `otdf-sdk-mgr` and `otdf-local` import from this module so the on-disk
YAML formats (`scenarios.yaml`, `instance.yaml`) have exactly one canonical
definition.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from ruamel.yaml import YAML, YAMLError

API_VERSION = "opentdf.io/v1alpha1"

KasMode = Literal["standard", "key_management"]
SdkName = Literal["go", "java", "js"]
ContainerKind = Literal["ztdf", "ztdf-ecwrap", "nano", "nano-with-policy"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


class SourceRef(_StrictModel):
    ref: str = Field(description="Git tag, branch, or SHA")
    path: Path | None = Field(default=None, description="Optional local checkout path")


class PlatformPin(_StrictModel):
    """Version pin for the platform service.

    `dist` references a built binary at `xtest/platform/dist/<dist>/service`
    produced by `otdf-sdk-mgr install platform:<version>`. `source.ref` is a
    git ref to build from on demand. `image` is reserved for forward-compat
    once container images are published; rejected at run time today.
    """

    dist: str | None = None
    source: SourceRef | None = None
    image: str | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> PlatformPin:
        set_fields = [k for k in ("dist", "source", "image") if getattr(self, k) is not None]
        if len(set_fields) != 1:
            raise ValueError(
                f"PlatformPin must set exactly one of dist|source|image (got {set_fields or 'none'})"
            )
        return self


class KasPin(_StrictModel):
    """Per-KAS-instance version + mode pin."""

    dist: str | None = None
    source: SourceRef | None = None
    image: str | None = None
    mode: KasMode = "standard"
    features: dict[str, bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _exactly_one(self) -> KasPin:
        set_fields = [k for k in ("dist", "source", "image") if getattr(self, k) is not None]
        if len(set_fields) != 1:
            raise ValueError(
                f"KasPin must set exactly one of dist|source|image (got {set_fields or 'none'})"
            )
        return self


class SdkPin(_StrictModel):
    """SDK version pin (forwarded to otdf-sdk-mgr's existing resolve())."""

    version: str
    source: str | None = Field(
        default=None,
        description='For Go: "platform" to use the monorepo module path',
    )


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
    features: dict[str, bool] = Field(default_factory=dict)
    fixtures: Fixtures = Field(default_factory=Fixtures)


class ScenarioSdks(_StrictModel):
    """Encrypt/decrypt split mirrors xtest's --sdks-encrypt/--sdks-decrypt.

    Listing the same SDK in both maps reproduces the legacy "all pairs" mode.
    """

    encrypt: dict[SdkName, SdkPin] = Field(default_factory=dict)
    decrypt: dict[SdkName, SdkPin] = Field(default_factory=dict)

    def union(self) -> dict[SdkName, SdkPin]:
        """Return the union of encrypt+decrypt SDK pins (decrypt wins on conflict)."""
        return {**self.encrypt, **self.decrypt}


class Suite(_StrictModel):
    """Pytest selection + flags."""

    select: str = Field(description="Pytest -k or path::node selector")
    containers: ContainerKind | None = Field(default=None, description="Forwarded to --containers")
    markers: str | None = Field(default=None, description="Forwarded to -m")
    extra_args: list[str] = Field(default_factory=list)


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


def _load_yaml_mapping(path: str | Path) -> dict[str, object]:
    p = Path(path)
    raw = _yaml().load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{p}: top-level YAML must be a mapping, got {type(raw).__name__}")
    return raw


def load_scenario(path: str | Path) -> Scenario:
    """Parse and validate a scenarios.yaml file."""
    return Scenario.model_validate(_load_yaml_mapping(path))


def load_instance(path: str | Path) -> Instance:
    """Parse and validate an instance.yaml file."""
    return Instance.model_validate(_load_yaml_mapping(path))


def dump_instance(instance: Instance, path: str | Path) -> None:
    """Serialize an Instance to YAML at `path`."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = instance.model_dump(mode="json", exclude_none=True)
    y = _yaml()
    with p.open("w", encoding="utf-8") as f:
        y.dump(data, f)


def _main(argv: list[str] | None = None) -> int:
    """`python -m otdf_sdk_mgr.schema validate <path>` entry point."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "validate":
        print("usage: python -m otdf_sdk_mgr.schema validate <path>", file=sys.stderr)
        return 2
    path = Path(args[1])
    try:
        raw = _load_yaml_mapping(path)
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
