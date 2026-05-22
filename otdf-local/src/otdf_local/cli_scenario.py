"""`otdf-local scenario` subcommands.

Today's surface area is intentionally narrow — `run` is the only command
that's part of the bug-repro MVP. Bisect and other higher-level loops are
deferred (see plan §9).
"""

from __future__ import annotations

import json
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
    # Strip leading "xtest/" from targets — pytest runs from within xtest_root,
    # so paths prefixed with "xtest/" would be resolved as "xtest/xtest/...".
    args: list[str] = [
        t.removeprefix("xtest/") if t.startswith("xtest/") else t for t in suite.targets
    ]

    tokens = scenario_to_pytest_sdks(scenario, installed_json_for(scenario_path))
    if tokens["encrypt"]:
        args.extend(["--sdks-encrypt", " ".join(tokens["encrypt"])])
    if tokens["decrypt"]:
        args.extend(["--sdks-decrypt", " ".join(tokens["decrypt"])])
    if suite.containers:
        args.extend(["--containers", " ".join(suite.containers)])
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
        typer.echo(
            "Error: scenario.instance.metadata.name not set; pass --instance", err=True
        )
        raise typer.Exit(2)

    settings = get_settings()
    # Force the chosen instance via env so child pytest invocations agree.
    os.environ["OTDF_LOCAL_INSTANCE_NAME"] = instance_name

    # Tell xtest's load_otdfctl() which dist to use for the otdfctl admin CLI.
    # Without this it falls back to sdk/go/dist/main/otdfctl.sh (hardcoded
    # "main"), which doesn't exist when the resolved dist name is e.g. "vmain".
    try:
        installed_data = json.loads(
            installed_json_for(path).read_text(encoding="utf-8")
        )
        go_dists = [
            Path(e["path"]).name
            for role in ("encrypt", "decrypt")
            for e in installed_data.get("sdks", {}).get(role, [])
            if isinstance(e, dict) and e.get("sdk") == "go" and e.get("path")
        ]
        if go_dists:
            os.environ["OTDFCTL_HEADS"] = json.dumps(list(dict.fromkeys(go_dists)))
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass

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
