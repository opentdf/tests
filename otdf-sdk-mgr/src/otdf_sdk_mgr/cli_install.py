"""Install subcommand group for otdf-sdk-mgr."""

from __future__ import annotations

from typing import Annotated, Optional

import typer

from otdf_sdk_mgr.config import ALL_SDKS

install_app = typer.Typer(help="Install SDK CLI artifacts from registries or source.")


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
    from otdf_sdk_mgr.installers import cmd_lts

    cmd_lts(sdks or ALL_SDKS)


@install_app.command()
def tip(
    sdks: Annotated[
        Optional[list[str]],
        typer.Argument(help="SDKs to build from source (default: all)"),
    ] = None,
) -> None:
    """Source checkout + build from main."""
    from otdf_sdk_mgr.installers import cmd_tip

    cmd_tip(sdks or ALL_SDKS)


@install_app.command()
def release(
    specs: Annotated[
        list[str],
        typer.Argument(help="Version specs as SDK:VERSION (e.g., go:v0.24.0)"),
    ],
) -> None:
    """Install specific released versions."""
    from otdf_sdk_mgr.installers import cmd_release

    cmd_release(specs)


@install_app.command()
def artifact(
    sdk: Annotated[str, typer.Option(help="SDK to install")] = "",
    version: Annotated[str, typer.Option(help="Version to install")] = "",
    dist_name: Annotated[
        Optional[str], typer.Option("--dist-name", help="Override dist directory name")
    ] = None,
) -> None:
    """Install a single SDK version (used by CI)."""
    if not sdk or not version:
        typer.echo("Error: --sdk and --version are required", err=True)
        raise typer.Exit(1)
    from otdf_sdk_mgr.installers import cmd_install

    cmd_install(sdk, version, dist_name=dist_name)
