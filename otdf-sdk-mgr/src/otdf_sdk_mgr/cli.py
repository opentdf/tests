"""Main CLI application for otdf-sdk-mgr."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from otdf_sdk_mgr.cli_install import exit_with_error, install_app
from otdf_sdk_mgr.cli_versions import versions_app
from otdf_sdk_mgr.config import ALL_SDKS, get_sdk_dirs

app = typer.Typer(
    name="otdf-sdk-mgr",
    help="SDK artifact management CLI for OpenTDF cross-client tests.",
    no_args_is_help=True,
)

app.add_typer(install_app, name="install")
app.add_typer(versions_app, name="versions")


def _checkout_one(sdk: str, branch: str) -> None:
    """Check out one SDK's source as `install tip` does, without building it."""
    from otdf_sdk_mgr.checkout import checkout_go_from_platform, checkout_sdk_branch

    # otdfctl's source is in the platform monorepo; see installers.cmd_tip.
    if sdk == "go":
        checkout_go_from_platform(branch)
    else:
        checkout_sdk_branch(sdk, branch)


@app.command()
def checkout(
    sdk: Annotated[
        str | None,
        typer.Argument(help="SDK to checkout (go, js, java)"),
    ] = None,
    branch: Annotated[str, typer.Argument(help="Branch to checkout")] = "main",
    all_sdks: Annotated[bool, typer.Option("--all", help="Checkout all SDKs")] = False,
) -> None:
    """Clone bare repo and create/update worktree for an SDK branch."""
    try:
        if all_sdks:
            for s in ALL_SDKS:
                _checkout_one(s, branch)
        elif sdk:
            _checkout_one(sdk, branch)
        else:
            typer.echo("Error: provide an SDK name or use --all", err=True)
            raise typer.Exit(1)
    except typer.Exit:
        raise  # typer.Exit is a RuntimeError; this one is already reported
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as e:
        # `install tip`'s set, but ValueError rather than its subclass
        # CheckoutError, so that an unknown SDK name is reported too.
        exit_with_error(e)


@app.command()
def clean(
    dist_only: Annotated[
        bool, typer.Option("--dist-only", help="Only remove dist directories")
    ] = False,
    src_only: Annotated[
        bool, typer.Option("--src-only", help="Only remove source worktrees")
    ] = False,
) -> None:
    """Remove dist directories and/or source worktrees."""
    remove_dist = not src_only
    remove_src = not dist_only

    sdk_dirs = get_sdk_dirs()
    for sdk in ALL_SDKS:
        sdk_dir = sdk_dirs[sdk]
        if remove_dist:
            dist_dir = sdk_dir / "dist"
            if dist_dir.exists():
                shutil.rmtree(dist_dir)
                typer.echo(f"Removed {dist_dir}")

        if remove_src:
            src_dir = sdk_dir / "src"
            if src_dir.exists():
                for entry in sorted(src_dir.iterdir()):
                    if entry.name.endswith(".git"):
                        continue
                    if entry.is_dir():
                        shutil.rmtree(entry)
                        typer.echo(f"Removed {entry}")


@app.command("java-fixup")
def java_fixup(
    base_dir: Annotated[
        Path | None,
        typer.Argument(help="Base directory for Java source trees"),
    ] = None,
) -> None:
    """Fix pom.xml platform.branch property in Java SDK source trees."""
    from otdf_sdk_mgr.java_fixup import post_checkout_java_fixup

    post_checkout_java_fixup(base_dir)
