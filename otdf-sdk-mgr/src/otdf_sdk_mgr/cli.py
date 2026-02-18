"""Main CLI application for otdf-sdk-mgr."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated, Optional

import typer

from otdf_sdk_mgr.cli_install import install_app
from otdf_sdk_mgr.cli_versions import versions_app
from otdf_sdk_mgr.config import ALL_SDKS, get_sdk_dirs

app = typer.Typer(
    name="otdf-sdk-mgr",
    help="SDK artifact management CLI for OpenTDF cross-client tests.",
    no_args_is_help=True,
)

app.add_typer(install_app, name="install")
app.add_typer(versions_app, name="versions")


@app.command()
def checkout(
    sdk: Annotated[
        Optional[str],
        typer.Argument(help="SDK to checkout (go, js, java)"),
    ] = None,
    branch: Annotated[str, typer.Argument(help="Branch to checkout")] = "main",
    all_sdks: Annotated[bool, typer.Option("--all", help="Checkout all SDKs")] = False,
) -> None:
    """Clone bare repo and create/update worktree for an SDK branch."""
    from otdf_sdk_mgr.checkout import checkout_sdk_branch

    if all_sdks:
        for s in ALL_SDKS:
            checkout_sdk_branch(s, branch)
    elif sdk:
        checkout_sdk_branch(sdk, branch)
    else:
        typer.echo("Error: provide an SDK name or use --all", err=True)
        raise typer.Exit(1)


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
        Optional[Path],
        typer.Argument(help="Base directory for Java source trees"),
    ] = None,
) -> None:
    """Fix pom.xml platform.branch property in Java SDK source trees."""
    from otdf_sdk_mgr.java_fixup import post_checkout_java_fixup

    post_checkout_java_fixup(base_dir)
