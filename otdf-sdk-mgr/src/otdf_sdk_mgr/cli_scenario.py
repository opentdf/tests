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

from otdf_sdk_mgr.config import get_sdk_dirs
from otdf_sdk_mgr.installers import InstallError, install_go_from_platform, install_release
from otdf_sdk_mgr.platform_installer import (
    PlatformInstallError,
    install_helper_scripts,
    install_platform_release,
    install_platform_source,
)
from otdf_sdk_mgr.schema import (
    Instance,
    KasPin,
    PlatformPin,
    Scenario,
    load_yaml_mapping,
)
from otdf_sdk_mgr.semver import normalize_version


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

    from ruamel.yaml.error import YAMLError

    try:
        raw = load_yaml_mapping(path)
    except YAMLError as e:
        typer.echo(f"Error: {path} is not valid YAML: {e}", err=True)
        raise typer.Exit(1)

    kind = raw.get("kind") if isinstance(raw.get("kind"), str) else None
    scenario: Scenario | None = None
    if kind == "Scenario":
        scenario = Scenario.model_validate(raw)
        instance = scenario.instance
    elif kind == "Instance":
        instance = Instance.model_validate(raw)
    else:
        typer.echo(f"Error: {path} has unknown kind {kind!r}", err=True)
        raise typer.Exit(1)

    installed_platform: dict[str, str] | None = None
    installed_kas: dict[str, dict[str, str]] = {}
    installed_sdks: dict[str, list[dict[str, str | None]]] = {"encrypt": [], "decrypt": []}
    out = path.parent / f"{path.stem}.installed.json"

    def _snapshot(status: str | None = None) -> dict[str, object]:
        snap: dict[str, object] = {
            "manifest": str(path),
            "platform": installed_platform,
            "kas": installed_kas,
            "sdks": installed_sdks,
        }
        if status is not None:
            snap["status"] = status
        return snap

    try:
        installed_platform = _install_platform_pin(instance.platform)
        for kas_name, kas_pin in instance.kas.items():
            installed_kas[kas_name] = _install_platform_pin(kas_pin)
        if not skip_scripts:
            install_helper_scripts()

        if scenario is not None:
            install_paths: dict[tuple[str, str, str | None], str] = {}
            for entry in scenario.sdks.union():
                if entry.sdk == "go" and entry.source == "platform":
                    sdk_dirs = get_sdk_dirs()
                    dist_dir = sdk_dirs["go"] / "dist" / normalize_version(entry.version)
                    install_go_from_platform(entry.version, dist_dir)
                else:
                    dist_dir = install_release(entry.sdk, entry.version)
                install_paths[entry.install_key()] = str(dist_dir)
            for role in ("encrypt", "decrypt"):
                installed_sdks[role] = [
                    {
                        "sdk": entry.sdk,
                        "version": entry.version,
                        "source": entry.source,
                        "path": install_paths[entry.install_key()],
                    }
                    for entry in getattr(scenario.sdks, role)
                ]
    except (PlatformInstallError, InstallError) as e:
        out.write_text(json.dumps(_snapshot(status="partial"), indent=2) + "\n")
        typer.echo(f"Error: {e}", err=True)
        typer.echo(f"  Wrote partial manifest to {out}", err=True)
        raise typer.Exit(1)

    out.write_text(json.dumps(_snapshot(), indent=2) + "\n")
    typer.echo(f"  Wrote {out}")
