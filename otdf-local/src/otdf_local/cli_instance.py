"""`otdf-local instance` subcommands: init / ls / rm."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated, Optional

import typer
from otdf_sdk_mgr.schema import (
    Instance,
    Metadata,
    PlatformPin,
    PortsConfig,
    dump_instance,
)

from otdf_local.config.settings import Settings, get_settings
from otdf_local.utils.keys import ensure_keys_exist, generate_root_key
from otdf_local.utils.yaml import copy_yaml_with_updates

instance_app = typer.Typer(help="Manage named test environment instances.")


@instance_app.command("init")
def init(
    name: Annotated[str, typer.Argument(help="Instance name (used as directory name)")],
    from_scenario: Annotated[
        Optional[Path],
        typer.Option(
            "--from-scenario", help="Initialize from a scenarios.yaml or instance.yaml"
        ),
    ] = None,
    ports_base: Annotated[
        int,
        typer.Option(
            "--ports-base", help="Base port (KAS ports computed as base+N*101)"
        ),
    ] = 8080,
    platform_dist: Annotated[
        Optional[str],
        typer.Option("--platform", help="Platform dist version (e.g., v0.9.0)"),
    ] = None,
) -> None:
    """Scaffold a new instance directory at tests/instances/<name>/."""
    settings = get_settings()
    instance_dir = settings.instances_root / name

    if from_scenario is not None:
        _init_from_scenario(name, from_scenario, instance_dir)
    else:
        if platform_dist is None:
            typer.echo(
                "Error: --platform <dist> is required when not using --from-scenario",
                err=True,
            )
            raise typer.Exit(2)
        _init_minimal(name, instance_dir, ports_base, platform_dist)

    _validate_port_uniqueness(settings.instances_root, name)
    typer.echo(f"  Initialized instance '{name}' at {instance_dir}")


def _init_from_scenario(name: str, scenario_path: Path, instance_dir: Path) -> None:
    """Copy the embedded Instance from a Scenario or load a standalone Instance."""
    from otdf_sdk_mgr.schema import load_instance, load_scenario
    from ruamel.yaml import YAML

    y = YAML(typ="safe")
    raw = y.load(scenario_path.read_text())
    if not isinstance(raw, dict):
        raise typer.BadParameter(f"{scenario_path} top-level YAML must be a mapping")
    kind = raw.get("kind")
    if kind == "Scenario":
        scenario = load_scenario(scenario_path)
        instance = scenario.instance
    elif kind == "Instance":
        instance = load_instance(scenario_path)
    else:
        raise typer.BadParameter(f"{scenario_path} has unknown kind {kind!r}")
    # Ensure the metadata name matches the chosen directory name.
    instance.metadata.name = name
    instance_dir.mkdir(parents=True, exist_ok=True)
    (instance_dir / "kas").mkdir(parents=True, exist_ok=True)
    (instance_dir / "keys").mkdir(mode=0o700, parents=True, exist_ok=True)
    (instance_dir / "logs").mkdir(parents=True, exist_ok=True)
    dump_instance(instance, instance_dir / "instance.yaml")
    _provision_instance_dir(instance_dir, instance)


def _init_minimal(
    name: str, instance_dir: Path, ports_base: int, platform_dist: str
) -> None:
    """Create a barebones instance.yaml with default KAS layout."""
    instance = Instance(
        metadata=Metadata(name=name),
        platform=PlatformPin(dist=platform_dist),
        ports=PortsConfig(base=ports_base),
        kas={},
    )
    instance_dir.mkdir(parents=True, exist_ok=True)
    (instance_dir / "kas").mkdir(parents=True, exist_ok=True)
    (instance_dir / "keys").mkdir(mode=0o700, parents=True, exist_ok=True)
    (instance_dir / "logs").mkdir(parents=True, exist_ok=True)
    dump_instance(instance, instance_dir / "instance.yaml")
    _provision_instance_dir(instance_dir, instance)


def _resolve_platform_worktree(instance: Instance) -> Path:
    """Find the platform source worktree for this instance's pin.

    For both `dist` and `source` pins, the platform installer writes a
    `.version` file next to the binary with `worktree=<path>`. We follow
    that pointer because the binary's parent directory only holds the
    built artifact — the YAML templates live in the source tree.
    """
    from otdf_sdk_mgr.platform_installer import get_platform_dir
    from otdf_sdk_mgr.refs import expand_pr_shorthand, ref_slug

    settings = Settings()
    pin = instance.platform
    if pin.dist is not None:
        dist_name = pin.dist
    elif pin.source is not None:
        dist_name = ref_slug(expand_pr_shorthand(pin.source.ref))
    else:
        raise typer.BadParameter("instance.platform must set dist or source")

    binary = get_platform_dir() / "dist" / dist_name / "service"
    if not binary.exists():
        raise FileNotFoundError(
            f"Platform binary not found at {binary}. "
            f"Run `otdf-sdk-mgr install scenario` (or `install release platform:<v>`) "
            f"to provision it before `instance init`."
        )
    version_file = binary.parent / ".version"
    if version_file.exists():
        for line in version_file.read_text().splitlines():
            if line.startswith("worktree="):
                worktree = Path(line.split("=", 1)[1].strip())
                if worktree.is_dir():
                    return worktree
    # Fallback to sibling platform dir (legacy single-instance layout).
    if settings.platform_dir is not None:
        return settings.platform_dir
    raise FileNotFoundError(
        f"Could not resolve platform source worktree from {version_file}; "
        f"no sibling platform/ directory available either."
    )


def _provision_instance_dir(instance_dir: Path, instance: Instance) -> None:
    """Generate the bootstrap bundle: keys + opentdf.yaml with a fresh root_key.

    Idempotent — `ensure_keys_exist` skips files that already exist, and
    `opentdf.yaml` is only generated when missing so reruns of `instance init`
    don't churn the per-instance root_key.
    """
    keys_dir = instance_dir / "keys"
    keys_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    ensure_keys_exist(keys_dir)

    config_path = instance_dir / "opentdf.yaml"
    if config_path.exists():
        return

    worktree = _resolve_platform_worktree(instance)
    template = worktree / "opentdf-dev.yaml"
    if not template.is_file():
        template = worktree / "opentdf-example.yaml"
    if not template.is_file():
        raise FileNotFoundError(
            f"No platform config template found in {worktree} "
            f"(looked for opentdf-dev.yaml and opentdf-example.yaml)."
        )

    copy_yaml_with_updates(
        template,
        config_path,
        {"services.kas.root_key": generate_root_key()},
    )


def _validate_port_uniqueness(instances_root: Path, new_name: str) -> None:
    """Warn if another instance shares the same `ports.base`."""
    from otdf_sdk_mgr.schema import load_instance

    new_yaml = instances_root / new_name / "instance.yaml"
    if not new_yaml.exists():
        return
    new_inst = load_instance(new_yaml)
    new_base = new_inst.ports.base
    if not instances_root.exists():
        return
    for child in instances_root.iterdir():
        if not child.is_dir() or child.name == new_name:
            continue
        other_yaml = child / "instance.yaml"
        if not other_yaml.is_file():
            continue
        try:
            other = load_instance(other_yaml)
        except Exception:
            continue
        if other.ports.base == new_base:
            typer.echo(
                f"  Warning: instance '{child.name}' already uses ports.base={new_base}; "
                f"running both simultaneously will collide. Change one with `otdf-local instance init`.",
                err=True,
            )


@instance_app.command("ls")
def ls(
    as_json: Annotated[bool, typer.Option("--json", "-j", help="Emit JSON")] = False,
) -> None:
    """List known instances."""
    import json as _json

    from otdf_sdk_mgr.schema import load_instance

    settings = get_settings()
    root = settings.instances_root
    if not root.exists():
        if as_json:
            typer.echo(_json.dumps([]))
        else:
            typer.echo("  (no instances yet)")
        return
    rows: list[dict[str, object]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        ymp = child / "instance.yaml"
        if not ymp.is_file():
            continue
        try:
            inst = load_instance(ymp)
        except Exception as e:
            rows.append({"name": child.name, "error": str(e)})
            continue
        rows.append(
            {
                "name": child.name,
                "platform": (
                    inst.platform.dist
                    or (inst.platform.source.ref if inst.platform.source else "unknown")
                ),
                "ports_base": inst.ports.base,
                "kas": list(inst.kas.keys()),
            }
        )
    if as_json:
        typer.echo(_json.dumps(rows, indent=2))
    else:
        for row in rows:
            typer.echo(f"  {row}")


@instance_app.command("rm")
def rm(
    name: Annotated[str, typer.Argument(help="Instance to remove")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Remove an instance directory."""
    settings = get_settings()
    instance_dir = settings.instances_root / name
    if not instance_dir.exists():
        typer.echo(f"Error: instance '{name}' not found at {instance_dir}", err=True)
        raise typer.Exit(1)
    if not yes:
        confirm = typer.confirm(f"Delete {instance_dir}?", default=False)
        if not confirm:
            typer.echo("aborted")
            raise typer.Exit(1)
    shutil.rmtree(instance_dir)
    typer.echo(f"  Removed {instance_dir}")
