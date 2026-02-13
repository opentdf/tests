#!/usr/bin/env python3
"""Backward-compatible wrapper. Use `otdf-sdk-mgr versions list` instead.

Also re-exports key functions for any code that imports this module directly.
"""

import sys
from pathlib import Path

# tests/otdf-sdk-mgr/src/ is three levels up from xtest/sdk/scripts/
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent.parent.parent / "otdf-sdk-mgr" / "src"),
)

# Backward-compat: list-versions.py main() with argparse
import argparse  # noqa: E402
import json  # noqa: E402
from typing import Any  # noqa: E402

from otdf_sdk_mgr.registry import (  # noqa: E402, F401
    apply_filters,
    list_go_versions,
    list_java_github_releases,
    list_java_maven_versions,
    list_js_versions,
)
from otdf_sdk_mgr.semver import (  # noqa: E402, F401
    is_stable,
    parse_semver,
    semver_sort_key,
)


def print_table(entries: list[dict[str, Any]]) -> None:
    if not entries:
        print("(no results)")
        return
    cols = {
        "sdk": 6,
        "version": 20,
        "source": 16,
        "stable": 7,
        "has_cli": 8,
        "install_method": 60,
    }
    header = "  ".join(k.upper().ljust(v) for k, v in cols.items())
    print(header)
    print("-" * len(header))
    for entry in entries:
        row = []
        for key, width in cols.items():
            val = entry.get(key, "")
            if isinstance(val, bool):
                val = "yes" if val else "no"
            row.append(str(val)[:width].ljust(width))
        print("  ".join(row))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List available released versions of OpenTDF SDK CLIs."
    )
    parser.add_argument(
        "sdk",
        nargs="?",
        default="all",
        choices=["go", "js", "java", "all"],
        help="SDK to query (default: all)",
    )
    parser.add_argument(
        "--stable",
        action="store_true",
        help="Only show stable (non-prerelease) versions",
    )
    parser.add_argument(
        "--latest",
        type=int,
        default=None,
        metavar="N",
        help="Show only the N most recent versions per source",
    )
    parser.add_argument(
        "--releases",
        action="store_true",
        help="Include GitHub Releases info for Java (slower)",
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json",
        action="store_true",
        default=True,
        dest="output_json",
        help="JSON output (default)",
    )
    output_group.add_argument(
        "--table",
        action="store_true",
        help="Human-readable table output",
    )
    args = parser.parse_args()

    sdks = ["go", "js", "java"] if args.sdk == "all" else [args.sdk]
    all_entries: list[dict[str, Any]] = []

    for sdk in sdks:
        if sdk == "go":
            entries = list_go_versions()
            all_entries.extend(
                apply_filters(entries, stable_only=args.stable, latest_n=args.latest)
            )
        elif sdk == "js":
            entries = list_js_versions()
            all_entries.extend(
                apply_filters(entries, stable_only=args.stable, latest_n=args.latest)
            )
        elif sdk == "java":
            maven_entries = list_java_maven_versions()
            all_entries.extend(
                apply_filters(
                    maven_entries, stable_only=args.stable, latest_n=args.latest
                )
            )
            if args.releases:
                gh_entries = list_java_github_releases()
                all_entries.extend(
                    apply_filters(
                        gh_entries, stable_only=args.stable, latest_n=args.latest
                    )
                )

    if args.table:
        print_table(all_entries)
    else:
        print(json.dumps(all_entries, indent=2))


if __name__ == "__main__":
    main()
