"""`otdf-local scenario` subcommands.

Today's surface area is intentionally narrow — `run` is the only command
that's part of the bug-repro MVP. Bisect and other higher-level loops are
deferred (see plan §9).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from otdf_sdk_mgr.schema import (
    Scenario,
    installed_json_for,
    load_scenario,
    scenario_to_pytest_sdks,
)

from otdf_local.config.settings import get_settings

scenario_app = typer.Typer(help="Run scenarios.yaml against a healthy instance.")


def _build_pytest_args(scenario: Scenario, scenario_path: Path) -> list[str]:
    """Translate the scenario's `suite` block into pytest CLI args.

    SDK pins go through `scenario_to_pytest_sdks` so they're forwarded as
    the `sdk@<resolved-dist>` tokens xtest's #446 specifier format expects.
    Requires that `otdf-sdk-mgr install scenario` has been run first; the
    helper raises FileNotFoundError with a clean hint otherwise.
    """
    suite = scenario.suite
    args: list[str] = [suite.select]

    tokens = scenario_to_pytest_sdks(scenario, installed_json_for(scenario_path))
    if tokens["encrypt"]:
        args.extend(["--sdks-encrypt", " ".join(tokens["encrypt"])])
    if tokens["decrypt"]:
        args.extend(["--sdks-decrypt", " ".join(tokens["decrypt"])])
    if suite.containers:
        args.extend(["--containers", suite.containers])
    if suite.markers:
        args.extend(["-m", suite.markers])
    args.extend(suite.extra_args)
    return args


@scenario_app.command("run")
def run(
    path: Annotated[Path, typer.Argument(help="Path to scenarios.yaml")],
    instance: Annotated[
        str | None,
        typer.Option(
            "--instance",
            help="Override which instance to use (defaults to scenario.instance.metadata.name)",
        ),
    ] = None,
    extra: Annotated[
        list[str] | None,
        typer.Argument(help="Extra args passed through to pytest (after --)"),
    ] = None,
) -> None:
    """Run the pytest suite declared by the scenario against its instance."""
    if not path.exists():
        typer.echo(f"Error: {path} not found", err=True)
        raise typer.Exit(1)

    scenario = load_scenario(path)
    instance_name = instance or scenario.instance.metadata.name
    if not instance_name:
        typer.echo("Error: scenario.instance.metadata.name not set; pass --instance", err=True)
        raise typer.Exit(2)

    settings = get_settings()
    # Force the chosen instance via env so child pytest invocations agree.
    os.environ["OTDF_LOCAL_INSTANCE_NAME"] = instance_name

    xtest_root = settings.xtest_root
    if not xtest_root.exists():
        typer.echo(f"Error: xtest root not found at {xtest_root}", err=True)
        raise typer.Exit(1)

    try:
        pytest_args = _build_pytest_args(scenario, path)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    if extra:
        pytest_args.extend(extra)

    cmd = ["uv", "run", "pytest", *pytest_args]
    typer.echo(f"  Running: {' '.join(cmd)} (cwd={xtest_root})")
    completed = subprocess.run(cmd, cwd=xtest_root)
    raise typer.Exit(completed.returncode)
