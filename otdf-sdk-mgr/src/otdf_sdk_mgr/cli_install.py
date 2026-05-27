"""Install subcommand group for otdf-sdk-mgr."""

from __future__ import annotations

from typing import Annotated, Optional

import typer

from otdf_sdk_mgr.config import ALL_SDKS

install_app = typer.Typer(help="Install SDK CLI artifacts from registries or source.")


def _register_scenario_cmd() -> None:
    from otdf_sdk_mgr.cli_scenario import install_scenario_cmd

    install_app.command("scenario")(install_scenario_cmd)


_register_scenario_cmd()


def _split_platform(sdks: list[str]) -> tuple[bool, list[str]]:
    """Return (platform_requested, sdks_without_platform)."""
    return ("platform" in sdks, [s for s in sdks if s != "platform"])


def _install_platform_or_exit(
    install_fn,
    version: str,
    *,
    dist_name: str | None = None,
) -> None:
    """Run a platform installer, mapping PlatformInstallError to typer.Exit(1)."""
    from otdf_sdk_mgr.platform_installer import PlatformInstallError

    try:
        if dist_name is None:
            install_fn(version)
        else:
            install_fn(version, dist_name=dist_name)
    except PlatformInstallError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


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
    from otdf_sdk_mgr.platform_installer import install_platform_release

    want_platform, sdk_targets = _split_platform(sdks or ALL_SDKS)
    if want_platform:
        version = LTS_VERSIONS.get("platform")
        if version is None:
            typer.echo("Error: no LTS version defined for platform", err=True)
            raise typer.Exit(1)
        _install_platform_or_exit(install_platform_release, version)
    if sdk_targets:
        cmd_lts(sdk_targets)


@install_app.command()
def tip(
    sdks: Annotated[
        Optional[list[str]],
        typer.Argument(help="SDKs to build from source (default: all)"),
    ] = None,
    ref: Annotated[
        str,
        typer.Option(
            "--ref",
            help=(
                "Git ref to build (branch, tag, SHA, `pr:N`, or `refs/...`). "
                "Default `main`. Mutable refs (branches, PR heads) are "
                "re-fetched and rebuilt on each invocation; immutable refs "
                "(tags, SHAs) reuse the existing build."
            ),
        ),
    ] = "main",
) -> None:
    """Source checkout + build at a git ref (default: main).

    Examples:
        otdf-sdk-mgr install tip                              # main, all SDKs
        otdf-sdk-mgr install tip --ref my-branch platform
        otdf-sdk-mgr install tip --ref pr:42 go
        otdf-sdk-mgr install tip --ref abc123f platform java
    """
    from otdf_sdk_mgr.installers import cmd_tip
    from otdf_sdk_mgr.platform_installer import install_platform_source

    want_platform, sdk_targets = _split_platform(sdks or ALL_SDKS)
    # Preserve historical `dist/tip/` naming when --ref is omitted; otherwise
    # let the platform installer slugify the ref.
    platform_dist_name = "tip" if ref == "main" else None
    if want_platform:
        _install_platform_or_exit(install_platform_source, ref, dist_name=platform_dist_name)
    if sdk_targets:
        cmd_tip(sdk_targets, ref=ref)


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
    from otdf_sdk_mgr.platform_installer import install_platform_release

    sdk_specs: list[str] = []
    for spec in specs:
        if ":" not in spec:
            typer.echo(f"Error: invalid spec '{spec}'. Use SDK:VERSION.", err=True)
            raise typer.Exit(1)
        sdk, version = spec.split(":", 1)
        if sdk == "platform":
            _install_platform_or_exit(install_platform_release, version)
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
) -> None:
    """Install a single SDK version (used by CI)."""
    from otdf_sdk_mgr.installers import InstallError, cmd_install

    try:
        cmd_install(sdk, version, dist_name=dist_name)
    except InstallError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
