"""Scenario-driven install command.

Reads a `scenarios.yaml` (or standalone `instance.yaml`) and installs every
artifact referenced — platform service binary, per-KAS binaries (each at
its own pinned version), and encrypt/decrypt SDK CLIs. Writes
`installed.json` next to the manifest so downstream tools (`otdf-local`,
plugin skills) can locate the dist paths without re-resolving.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from otdf_sdk_mgr.installers import InstallError, install_release
from otdf_sdk_mgr.platform_installer import (
    PlatformInstallError,
    install_helper_scripts,
    install_platform_release,
    install_platform_source,
)
from otdf_sdk_mgr.schema import KasPin, PlatformPin, Scenario, load_instance, load_scenario


def _install_platform_pin(pin: PlatformPin | KasPin) -> dict[str, str]:
    if pin.dist is not None:
        dist_dir = install_platform_release(pin.dist)
        return {"kind": "dist", "version": pin.dist, "path": str(dist_dir)}
    assert pin.source is not None  # by schema invariant
    dist_dir = install_platform_source(pin.source.ref)
    return {"kind": "source", "ref": pin.source.ref, "path": str(dist_dir)}


def install_scenario_cmd(
    path: Annotated[Path, typer.Argument(help="Path to scenarios.yaml or instance.yaml")],
    skip_scripts: Annotated[
        bool,
        typer.Option("--skip-scripts", help="Skip refreshing helper scripts from main"),
    ] = False,
) -> None:
    """Install every artifact declared by a scenarios.yaml or instance.yaml."""
    if not path.exists():
        typer.echo(f"Error: {path} not found", err=True)
        raise typer.Exit(1)

    raw_kind = _peek_kind(path)
    scenario: Scenario | None = None
    if raw_kind == "Scenario":
        scenario = load_scenario(path)
        instance = scenario.instance
    elif raw_kind == "Instance":
        instance = load_instance(path)
    else:
        typer.echo(f"Error: {path} has unknown kind {raw_kind!r}", err=True)
        raise typer.Exit(1)

    installed: dict[str, object] = {"manifest": str(path), "platform": None, "kas": {}, "sdks": {}}

    try:
        installed["platform"] = _install_platform_pin(instance.platform)
        for kas_name, kas_pin in instance.kas.items():
            installed["kas"][kas_name] = _install_platform_pin(kas_pin)
        if not skip_scripts:
            install_helper_scripts()
    except PlatformInstallError as e:
        typer.echo(f"Error installing platform artifacts: {e}", err=True)
        raise typer.Exit(1)

    if scenario is not None:
        sdks = scenario.sdks.union()
        for sdk_name, sdk_pin in sdks.items():
            try:
                dist_dir = install_release(sdk_name, sdk_pin.version, source=sdk_pin.source)
                installed["sdks"][sdk_name] = {
                    "version": sdk_pin.version,
                    "source": sdk_pin.source,
                    "path": str(dist_dir),
                }
            except InstallError as e:
                typer.echo(f"Error installing SDK {sdk_name}: {e}", err=True)
                raise typer.Exit(1)

    out = path.parent / f"{path.stem}.installed.json"
    out.write_text(json.dumps(installed, indent=2) + "\n")
    typer.echo(f"  Wrote {out}")


def _peek_kind(path: Path) -> str | None:
    """Cheap pre-validation read so we can dispatch to the right model loader."""
    from ruamel.yaml import YAML

    y = YAML(typ="safe")
    raw = y.load(path.read_text())
    if isinstance(raw, dict):
        kind = raw.get("kind")
        return kind if isinstance(kind, str) else None
    return None
