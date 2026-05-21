"""Versions subcommand group for otdf-sdk-mgr."""

from __future__ import annotations

import json
from typing import Annotated, Any, Optional

import typer
from rich.console import Console
from rich.table import Table

from otdf_sdk_mgr.config import SDK_GIT_URLS, SDK_TAG_INFIXES
from otdf_sdk_mgr.resolve import ResolveResult

versions_app = typer.Typer(help="Query SDK version registries.")


@versions_app.command("list")
def list_versions(
    sdk: Annotated[
        str,
        typer.Argument(help="SDK to query (go, js, java, all)"),
    ] = "all",
    stable: Annotated[bool, typer.Option("--stable", help="Only stable versions")] = False,
    latest: Annotated[
        Optional[int], typer.Option("--latest", help="Show only N most recent versions")
    ] = None,
    releases: Annotated[
        bool, typer.Option("--releases", help="Include GitHub Releases info for Java")
    ] = False,
    output_table: Annotated[
        bool, typer.Option("--table", help="Human-readable Rich table output")
    ] = False,
) -> None:
    """List available released versions of SDK CLIs."""
    from otdf_sdk_mgr.registry import (
        apply_filters,
        list_go_versions,
        list_java_github_releases,
        list_java_maven_versions,
        list_js_versions,
    )

    sdks = ["go", "js", "java"] if sdk == "all" else [sdk]
    all_entries: list[dict[str, Any]] = []

    for s in sdks:
        if s == "go":
            entries = list_go_versions()
            all_entries.extend(apply_filters(entries, stable_only=stable, latest_n=latest))
        elif s == "js":
            entries = list_js_versions()
            all_entries.extend(apply_filters(entries, stable_only=stable, latest_n=latest))
        elif s == "java":
            maven_entries = list_java_maven_versions()
            all_entries.extend(apply_filters(maven_entries, stable_only=stable, latest_n=latest))
            if releases:
                gh_entries = list_java_github_releases()
                all_entries.extend(apply_filters(gh_entries, stable_only=stable, latest_n=latest))

    if output_table:
        _print_rich_table(all_entries)
    else:
        print(json.dumps(all_entries, indent=2))


def _print_rich_table(entries: list[dict[str, Any]]) -> None:
    """Print entries as a Rich table."""
    if not entries:
        Console().print("[dim](no results)[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("SDK", width=6)
    table.add_column("VERSION", width=20)
    table.add_column("SOURCE", width=16)
    table.add_column("STABLE", width=7)
    table.add_column("HAS_CLI", width=8)
    table.add_column("INSTALL_METHOD", min_width=40)

    for entry in entries:
        stable_val = entry.get("stable", "")
        stable_str = "yes" if stable_val else "no" if stable_val is not None else ""
        has_cli_val = entry.get("has_cli", "")
        has_cli_str = "yes" if has_cli_val else "no" if has_cli_val is not None else ""
        table.add_row(
            str(entry.get("sdk", "")),
            str(entry.get("version", "")),
            str(entry.get("source", "")),
            stable_str,
            has_cli_str,
            str(entry.get("install_method", "")),
        )

    Console().print(table)


@versions_app.command("resolve")
def resolve_versions(
    sdk: Annotated[str, typer.Argument(help="SDK to resolve (go, js, java, platform)")],
    tags: Annotated[list[str], typer.Argument(help="Version tags to resolve")],
) -> None:
    """Resolve version tags to git SHAs."""
    from otdf_sdk_mgr.resolve import (
        is_resolve_success,
        lookup_additional_options,
        resolve,
    )

    if sdk not in SDK_GIT_URLS:
        typer.echo(f"Unknown SDK: {sdk}", err=True)
        raise typer.Exit(2)
    infix = SDK_TAG_INFIXES.get(sdk)

    results: list[ResolveResult] = []
    shas: set[str] = set()
    for version in tags:
        v = resolve(sdk, version, infix)
        if is_resolve_success(v):
            env = lookup_additional_options(sdk, v["tag"])
            if env:
                v["env"] = env
            if v["sha"] in shas:
                continue
            shas.add(v["sha"])
        results.append(v)

    print(json.dumps(results))
