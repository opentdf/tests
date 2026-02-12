#!/usr/bin/env python3
"""List available released versions of OpenTDF SDK CLIs.

Usage:
    python3 list-versions.py [sdk] [options]

Examples:
    python3 list-versions.py go                    # List all go versions
    python3 list-versions.py js --stable           # Only stable JS releases
    python3 list-versions.py java --releases       # Include GitHub Release assets
    python3 list-versions.py all --latest 5        # Last 5 versions of each SDK
    python3 list-versions.py all --latest 3 --table
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from typing import Any

sdk_git_urls = {
    "go": "https://github.com/opentdf/otdfctl.git",
    "java": "https://github.com/opentdf/java-sdk.git",
    "js": "https://github.com/opentdf/web-sdk.git",
}

sdk_npm_packages = {
    "js": "@opentdf/ctl",
}

sdk_maven_coords = {
    "java": {
        "group": "io.opentdf.platform",
        "artifact": "sdk",
        "base_url": "https://repo1.maven.org/maven2/io/opentdf/platform/sdk",
    },
}

sdk_github_repos = {
    "java": "opentdf/java-sdk",
}

go_install_prefix = "go run github.com/opentdf/otdfctl"

SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-(.+))?$")


def parse_semver(version: str) -> tuple[int, int, int, str | None] | None:
    m = SEMVER_RE.match(version)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)


def is_stable(version: str) -> bool:
    parsed = parse_semver(version)
    if parsed is None:
        return False
    return parsed[3] is None


def semver_sort_key(version: str) -> tuple[int, int, int, int, str]:
    parsed = parse_semver(version)
    if parsed is None:
        return (0, 0, 0, 0, version)
    major, minor, patch, pre = parsed
    # Stable versions sort after pre-release
    return (major, minor, patch, 0 if pre else 1, pre or "")


def fetch_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode()


def list_go_versions() -> list[dict[str, Any]]:
    """List Go SDK versions from git tags."""
    from git import Git

    repo = Git()
    raw = repo.ls_remote(sdk_git_urls["go"], tags=True)
    results = []
    for line in raw.strip().split("\n"):
        if not line:
            continue
        _, ref = line.split("\t", 1)
        if ref.endswith("^{}"):
            continue
        tag = ref.removeprefix("refs/tags/")
        if not parse_semver(tag):
            continue
        version = tag
        results.append(
            {
                "sdk": "go",
                "version": version,
                "source": "git-tag",
                "install_method": f"{go_install_prefix}@{version}",
                "stable": is_stable(version),
            }
        )
    results.sort(key=lambda r: semver_sort_key(r["version"]))
    return results


def list_js_versions() -> list[dict[str, Any]]:
    """List JS SDK versions from npm registry."""
    package = sdk_npm_packages["js"]
    url = f"https://registry.npmjs.org/{package}"
    try:
        data = fetch_json(url)
    except urllib.error.URLError as e:
        print(f"Warning: failed to fetch npm registry: {e}", file=sys.stderr)
        return []

    dist_tags: dict[str, str] = data.get("dist-tags", {})
    tag_lookup: dict[str, list[str]] = {}
    for tag_name, tag_version in dist_tags.items():
        tag_lookup.setdefault(tag_version, []).append(tag_name)

    versions_dict: dict[str, Any] = data.get("versions", {})
    results = []
    for version in versions_dict:
        if not parse_semver(version):
            continue
        entry: dict[str, Any] = {
            "sdk": "js",
            "version": version,
            "source": "npm",
            "install_method": f"npx {package}@{version}",
            "stable": is_stable(version),
        }
        if version in tag_lookup:
            entry["dist_tags"] = tag_lookup[version]
        results.append(entry)
    results.sort(key=lambda r: semver_sort_key(r["version"]))
    return results


def list_java_maven_versions() -> list[dict[str, Any]]:
    """List Java SDK versions from Maven Central metadata."""
    coords = sdk_maven_coords["java"]
    url = f"{coords['base_url']}/maven-metadata.xml"
    try:
        xml_text = fetch_text(url)
    except urllib.error.URLError as e:
        print(f"Warning: failed to fetch Maven metadata: {e}", file=sys.stderr)
        return []

    # Simple regex extraction — no XML library needed
    versions = re.findall(r"<version>([^<]+)</version>", xml_text)
    results = []
    for version in versions:
        if not parse_semver(version):
            continue
        results.append(
            {
                "sdk": "java",
                "version": version,
                "source": "maven",
                "stable": is_stable(version),
                "has_cli": False,
            }
        )
    results.sort(key=lambda r: semver_sort_key(r["version"]))
    return results


def list_java_github_releases() -> list[dict[str, Any]]:
    """List Java SDK versions from GitHub Releases (checks for cmdline.jar)."""
    repo = sdk_github_repos["java"]
    results = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{repo}/releases?per_page=100&page={page}"
        try:
            releases = fetch_json(url)
        except urllib.error.URLError as e:
            print(f"Warning: failed to fetch GitHub releases: {e}", file=sys.stderr)
            break
        if not releases:
            break
        for release in releases:
            tag = release.get("tag_name", "")
            if not parse_semver(tag):
                continue
            assets = release.get("assets", [])
            asset_names = [a["name"] for a in assets]
            has_cli = any("cmdline" in name for name in asset_names)
            entry: dict[str, Any] = {
                "sdk": "java",
                "version": tag,
                "source": "github-release",
                "stable": is_stable(tag) and not release.get("prerelease", False),
            }
            if asset_names:
                entry["artifacts"] = asset_names
            entry["has_cli"] = has_cli
            if has_cli:
                cli_asset = next(a for a in assets if "cmdline" in a["name"])
                entry["install_method"] = (
                    f"download from {cli_asset['browser_download_url']}"
                )
            results.append(entry)
        page += 1
    results.sort(key=lambda r: semver_sort_key(r["version"]))
    return results


def apply_filters(
    entries: list[dict[str, Any]],
    *,
    stable_only: bool = False,
    latest_n: int | None = None,
) -> list[dict[str, Any]]:
    if stable_only:
        entries = [e for e in entries if e.get("stable", False)]
    if latest_n is not None:
        entries = entries[-latest_n:]
    return entries


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
