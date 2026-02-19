"""Registry queries for SDK version discovery."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from otdf_sdk_mgr.config import (
    GO_INSTALL_PREFIX,
    SDK_GITHUB_REPOS,
    SDK_GIT_URLS,
    SDK_MAVEN_COORDS,
    SDK_NPM_PACKAGES,
)
from otdf_sdk_mgr.semver import is_stable, parse_semver, semver_sort_key


def _github_headers() -> dict[str, str]:
    """Return headers for GitHub API requests, including auth if GITHUB_TOKEN is set."""
    headers: dict[str, str] = {"Accept": "application/json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_json(url: str) -> Any:
    """Fetch JSON from a URL."""
    headers = {"Accept": "application/json"}
    if url.startswith("https://api.github.com/"):
        headers = _github_headers()
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (403, 429) and url.startswith("https://api.github.com/"):
            reset_ts = e.headers.get("X-RateLimit-Reset")
            if reset_ts:
                reset_time = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(reset_ts)))
                print(
                    f"Warning: GitHub API rate limit exceeded. "
                    f"Rate limit resets at {reset_time}. "
                    f"Set GITHUB_TOKEN to increase rate limits.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Warning: GitHub API returned {e.code}. "
                    f"Set GITHUB_TOKEN to authenticate requests.",
                    file=sys.stderr,
                )
            raise
        raise


def fetch_text(url: str) -> str:
    """Fetch text content from a URL."""
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode()


def list_go_versions() -> list[dict[str, Any]]:
    """List Go SDK versions from git tags."""
    from git import Git

    repo = Git()
    raw = repo.ls_remote(SDK_GIT_URLS["go"], tags=True)
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
                "install_method": f"{GO_INSTALL_PREFIX}@{version}",
                "stable": is_stable(version),
            }
        )
    results.sort(key=lambda r: semver_sort_key(r["version"]))
    return results


def list_js_versions() -> list[dict[str, Any]]:
    """List JS SDK versions from npm registry."""
    package = SDK_NPM_PACKAGES["js"]
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
    coords = SDK_MAVEN_COORDS["java"]
    url = f"{coords['base_url']}/maven-metadata.xml"
    try:
        xml_text = fetch_text(url)
    except urllib.error.URLError as e:
        print(f"Warning: failed to fetch Maven metadata: {e}", file=sys.stderr)
        return []

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
    repo = SDK_GITHUB_REPOS["java"]
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
                entry["install_method"] = f"download from {cli_asset['browser_download_url']}"
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
    """Filter version entries by stability and count."""
    if stable_only:
        entries = [e for e in entries if e.get("stable", False)]
    if latest_n is not None:
        entries = entries[-latest_n:]
    return entries
