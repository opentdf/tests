"""Install subcommand group for otdf-sdk-mgr."""

from __future__ import annotations

from typing import Annotated, Optional

import typer

from otdf_sdk_mgr.config import ALL_SDKS

install_app = typer.Typer(help="Install SDK CLI artifacts from registries or source.")


def _register_scenario_cmd() -> None:
    """Defer scenario import so pydantic is only imported when needed."""
    from otdf_sdk_mgr.cli_scenario import install_scenario_cmd

    install_app.command("scenario")(install_scenario_cmd)


_register_scenario_cmd()


@install_app.command()
def stable(
    sdks: Annotated[
        Optional[list[str]],
        typer.Argument(help="SDKs to install (default: all)"),
    ] = None,
) -> None:
    """Install latest stable releases for each SDK."""
    from otdf_sdk_mgr.installers import cmd_stable

    cmd_stable(sdks or ALL_SDKS)


@install_app.command()
def lts(
    sdks: Annotated[
        Optional[list[str]],
        typer.Argument(help="SDKs to install (default: all)"),
    ] = None,
) -> None:
    """Install LTS versions for each SDK."""
    from otdf_sdk_mgr.config import LTS_VERSIONS
    from otdf_sdk_mgr.installers import cmd_lts
    from otdf_sdk_mgr.platform_installer import (
        PlatformInstallError,
        install_platform_release,
    )

    requested = sdks or ALL_SDKS
    sdk_targets = [s for s in requested if s != "platform"]
    if "platform" in requested:
        version = LTS_VERSIONS.get("platform")
        if version is None:
            typer.echo("Warning: no LTS version defined for platform; skipping", err=True)
        else:
            try:
                install_platform_release(version)
            except PlatformInstallError as e:
                typer.echo(f"Error: {e}", err=True)
                raise typer.Exit(1)
    if sdk_targets:
        cmd_lts(sdk_targets)


@install_app.command()
def tip(
    sdks: Annotated[
        Optional[list[str]],
        typer.Argument(help="SDKs to build from source (default: all)"),
    ] = None,
) -> None:
    """Source checkout + build from main."""
    from otdf_sdk_mgr.installers import cmd_tip
    from otdf_sdk_mgr.platform_installer import (
        PlatformInstallError,
        install_platform_source,
    )

    requested = sdks or ALL_SDKS
    sdk_targets = [s for s in requested if s != "platform"]
    if "platform" in requested:
        try:
            install_platform_source("main", dist_name="tip")
        except PlatformInstallError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
    if sdk_targets:
        cmd_tip(sdk_targets)


@install_app.command()
def release(
    specs: Annotated[
        list[str],
        typer.Argument(help="Version specs as SDK:VERSION (e.g., go:v0.24.0, platform:v0.9.0)"),
    ],
) -> None:
    """Install specific released versions.

    `sdk` may be one of go/js/java or the literal `platform`. Platform is
    built from source against the `service/<version>` tag in the
    `opentdf/platform` monorepo.
    """
    from otdf_sdk_mgr.installers import InstallError, cmd_release
    from otdf_sdk_mgr.platform_installer import (
        PlatformInstallError,
        install_platform_release,
    )

    sdk_specs: list[str] = []
    for spec in specs:
        if ":" not in spec:
            typer.echo(f"Error: invalid spec '{spec}'. Use SDK:VERSION.", err=True)
            raise typer.Exit(1)
        sdk, version = spec.split(":", 1)
        if sdk == "platform":
            try:
                install_platform_release(version)
            except PlatformInstallError as e:
                typer.echo(f"Error: {e}", err=True)
                raise typer.Exit(1)
        else:
            sdk_specs.append(spec)
    if sdk_specs:
        try:
            cmd_release(sdk_specs)
        except InstallError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)


@install_app.command()
def scripts(
    branch: Annotated[
        str,
        typer.Option(help="Branch of opentdf/platform to pull scripts from"),
    ] = "main",
) -> None:
    """Refresh shared platform helper scripts under xtest/platform/scripts/."""
    from otdf_sdk_mgr.platform_installer import (
        PlatformInstallError,
        install_helper_scripts,
    )

    try:
        install_helper_scripts(branch)
    except PlatformInstallError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@install_app.command()
def artifact(
    sdk: Annotated[str, typer.Option(help="SDK to install")],
    version: Annotated[str, typer.Option(help="Version to install")],
    dist_name: Annotated[
        Optional[str], typer.Option("--dist-name", help="Override dist directory name")
    ] = None,
    source: Annotated[
        Optional[str],
        typer.Option(help='Source repo for Go CLI (e.g., "platform" for monorepo)'),
    ] = None,
) -> None:
    """Install a single SDK version (used by CI)."""
    from otdf_sdk_mgr.installers import InstallError, cmd_install

    try:
        cmd_install(sdk, version, dist_name=dist_name, source=source)
    except InstallError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
