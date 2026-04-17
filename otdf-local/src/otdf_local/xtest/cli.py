"""Typer CLI subcommands for xtest configuration and execution."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from otdf_local.config.settings import get_settings
from otdf_local.utils.console import console, print_error, print_success
from otdf_local.xtest.config import XtestConfig, XtestInputs

xtest_app = typer.Typer(
    name="xtest",
    help="Resolve, configure, and run xtest integration tests.",
    no_args_is_help=True,
)


@xtest_app.command()
def resolve(
    platform_ref: Annotated[
        str,
        typer.Option(
            "--platform-ref", help="Platform ref: branch, tag, SHA, 'latest', or 'lts'"
        ),
    ] = "main",
    go_ref: Annotated[
        str,
        typer.Option("--go-ref", help="Go/otdfctl ref"),
    ] = "main",
    js_ref: Annotated[
        str,
        typer.Option("--js-ref", help="JS/web-sdk ref"),
    ] = "main",
    java_ref: Annotated[
        str,
        typer.Option("--java-ref", help="Java SDK ref"),
    ] = "main",
    focus_sdk: Annotated[
        str,
        typer.Option("--focus-sdk", help="SDK to focus on (go, js, java, all)"),
    ] = "all",
    otdfctl_source: Annotated[
        str,
        typer.Option(
            "--otdfctl-source", help="otdfctl source: auto, standalone, platform"
        ),
    ] = "auto",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Write config to file (default: stdout)"),
    ] = None,
) -> None:
    """Resolve SDK versions and generate an xtest configuration file.

    Calls otdf-sdk-mgr to resolve version refs to SHAs, detects platform features,
    and outputs a YAML config suitable for `otdf-local xtest run`.
    """
    from otdf_local.xtest.resolve import resolve_all

    if focus_sdk not in ("all", "go", "js", "java"):
        print_error(
            f"Invalid focus-sdk: {focus_sdk}. Must be one of: all, go, js, java"
        )
        raise typer.Exit(1)

    inputs = XtestInputs(
        platform_ref=platform_ref,
        go_ref=go_ref,
        js_ref=js_ref,
        java_ref=java_ref,
        focus_sdk=focus_sdk,
        otdfctl_source=otdfctl_source,
    )

    settings = get_settings()
    config = resolve_all(inputs, settings)

    yaml_output = config.to_yaml()

    if output:
        config.to_yaml_file(output)
        print_success(f"Config written to {output}")
    else:
        print(yaml_output, file=sys.stdout)


@xtest_app.command()
def run(
    config_file: Annotated[
        Path,
        typer.Argument(help="Path to xtest config YAML file"),
    ],
    phase: Annotated[
        str | None,
        typer.Option(
            "--phase",
            "-p",
            help="Run only this phase (helpers, legacy, standard, abac)",
        ),
    ] = None,
    skip_services: Annotated[
        bool,
        typer.Option("--skip-services", help="Assume services are already running"),
    ] = False,
    skip_install: Annotated[
        bool,
        typer.Option("--skip-install", help="Assume SDKs are already installed"),
    ] = False,
) -> None:
    """Run xtest integration tests from a configuration file.

    Installs SDKs, starts services, and runs test phases as defined in the config.

    Example:
        otdf-local xtest run xtest-config.yaml
        otdf-local xtest run xtest-config.yaml --phase legacy --skip-services
    """
    from otdf_local.xtest.runner import run_xtest

    if not config_file.exists():
        print_error(f"Config file not found: {config_file}")
        raise typer.Exit(1)

    config = XtestConfig.from_yaml(config_file)
    settings = get_settings()

    passed = run_xtest(
        config=config,
        settings=settings,
        phase_name=phase,
        skip_services=skip_services,
        skip_install=skip_install,
    )

    if not passed:
        raise typer.Exit(1)


@xtest_app.command()
def show(
    config_file: Annotated[
        Path,
        typer.Argument(help="Path to xtest config YAML file"),
    ],
) -> None:
    """Display a human-readable summary of an xtest configuration."""
    if not config_file.exists():
        print_error(f"Config file not found: {config_file}")
        raise typer.Exit(1)

    config = XtestConfig.from_yaml(config_file)

    console.print(f"[bold]xtest config v{config.version}[/bold]")
    console.print(f"  Platform tag: {config.platform_tag}")
    console.print(f"  Encrypt SDK:  {config.encrypt_sdk}")
    console.print(f"  Focus SDK:    {config.inputs.focus_sdk}")
    console.print()

    # Versions table
    table = Table(title="Resolved Versions", show_header=True, header_style="bold")
    table.add_column("SDK", width=10)
    table.add_column("Tag", width=20)
    table.add_column("SHA", width=10)
    table.add_column("Type", width=10)
    table.add_column("Error", width=30)

    for sdk, versions in config.resolved.items():
        for v in versions:
            vtype = "head" if v.head else "release" if v.release else "?"
            table.add_row(
                sdk,
                v.tag,
                v.sha[:7] if v.sha else "",
                vtype,
                v.err or "",
            )

    console.print(table)
    console.print()

    # Features
    console.print("[bold]Features[/bold]")
    console.print(f"  EC TDF:          {config.features.ec_tdf}")
    console.print(f"  Key Management:  {config.features.key_management}")
    console.print(f"  Multi-KAS:       {config.features.multikas}")
    console.print()

    # Phases
    console.print("[bold]Test Phases[/bold]")
    for phase in config.phases:
        reqs = f" (requires: {', '.join(phase.requires)})" if phase.requires else ""
        met = config.check_phase_requirements(phase)
        status = "[green]ready[/green]" if met else "[yellow]skipped[/yellow]"
        console.print(f"  {status} {phase.name}: {', '.join(phase.test_files)}{reqs}")
