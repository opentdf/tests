"""Version resolution for SDK tags/branches/SHAs."""

from __future__ import annotations

import json
import re
import sys
from typing import NotRequired, TypedDict, TypeGuard

from git import Git

from otdf_sdk_mgr.config import (
    JAVA_PLATFORM_BRANCH_MAP,
    LTS_VERSIONS,
    SDK_GIT_URLS,
    SDK_TAG_INFIXES,
)


class ResolveSuccess(TypedDict):
    sdk: str
    alias: str
    env: NotRequired[str]
    head: NotRequired[bool]
    pr: NotRequired[str]
    release: NotRequired[str]
    sha: str
    tag: str


class ResolveError(TypedDict):
    sdk: str
    alias: str
    err: str


ResolveResult = ResolveSuccess | ResolveError


def is_resolve_error(val: ResolveResult) -> TypeGuard[ResolveError]:
    """Check if the given value is a ResolveError type."""
    return "err" in val


def is_resolve_success(val: ResolveResult) -> TypeGuard[ResolveSuccess]:
    """Check if the given value is a ResolveSuccess type."""
    return "err" not in val and "sha" in val and "tag" in val


MERGE_QUEUE_REGEX = (
    r"^refs/heads/gh-readonly-queue/(?P<branch>[^/]+)/pr-(?P<pr_number>\d+)-(?P<sha>[a-f0-9]{40})$"
)

SHA_REGEX = r"^[a-f0-9]{7,40}$"


def lookup_additional_options(sdk: str, version: str) -> str | None:
    """Look up additional build options for a given SDK version."""
    if sdk != "java":
        return None
    if version.startswith("v"):
        version = version[1:]
    branch = JAVA_PLATFORM_BRANCH_MAP.get(version)
    if branch:
        return f"PLATFORM_BRANCH={branch}"
    return None


def resolve(sdk: str, version: str, infix: str | None) -> ResolveResult:
    """Resolve a version spec to a concrete SHA and tag."""
    sdk_url = SDK_GIT_URLS[sdk]
    try:
        repo = Git()
        if version == "main" or version == "refs/heads/main":
            all_heads = [r.split("\t") for r in repo.ls_remote(sdk_url, heads=True).split("\n")]
            sha, _ = [tag for tag in all_heads if "refs/heads/main" in tag][0]
            return {
                "sdk": sdk,
                "alias": version,
                "head": True,
                "sha": sha,
                "tag": "main",
            }

        if re.match(SHA_REGEX, version):
            ls_remote = [r.split("\t") for r in repo.ls_remote(sdk_url).split("\n")]
            matching_tags = [(sha, tag) for (sha, tag) in ls_remote if sha.startswith(version)]
            if not matching_tags:
                return {
                    "sdk": sdk,
                    "alias": version[:7],
                    "sha": version,
                    "tag": version,
                }
            if len(matching_tags) > 1:
                for sha, tag in matching_tags:
                    if tag.startswith("refs/pull/"):
                        pr_number = tag.split("/")[2]
                        return {
                            "sdk": sdk,
                            "alias": version,
                            "head": True,
                            "sha": sha,
                            "tag": f"pull-{pr_number}",
                        }
                for sha, tag in matching_tags:
                    mq_match = re.match(MERGE_QUEUE_REGEX, tag)
                    if mq_match:
                        to_branch = mq_match.group("branch")
                        pr_number = mq_match.group("pr_number")
                        if to_branch and pr_number:
                            return {
                                "sdk": sdk,
                                "alias": version,
                                "head": True,
                                "pr": pr_number,
                                "sha": sha,
                                "tag": f"mq-{to_branch}-{pr_number}",
                            }
                        suffix = tag.split("refs/heads/gh-readonly-queue/")[-1]
                        flattag = "mq--" + suffix.replace("/", "--")
                        return {
                            "sdk": sdk,
                            "alias": version,
                            "head": True,
                            "sha": sha,
                            "tag": flattag,
                        }
                    head = False
                    if tag.startswith("refs/heads/"):
                        head = True
                        tag = tag.split("refs/heads/")[-1]
                    flattag = tag.replace("/", "--")
                    return {
                        "sdk": sdk,
                        "alias": version,
                        "head": head,
                        "sha": sha,
                        "tag": flattag,
                    }

                return {
                    "sdk": sdk,
                    "alias": version,
                    "err": (
                        f"SHA {version} points to multiple tags, unable to differentiate: "
                        f"{', '.join(tag for _, tag in matching_tags)}"
                    ),
                }
            (sha, tag) = matching_tags[0]
            if tag.startswith("refs/tags/"):
                tag = tag.split("refs/tags/")[-1]
            if infix:
                tag = tag.split(f"{infix}/")[-1]
            return {
                "sdk": sdk,
                "alias": version,
                "sha": sha,
                "tag": tag,
            }

        if version.startswith("refs/pull/"):
            merge_heads = [
                r.split("\t") for r in repo.ls_remote(sdk_url).split("\n") if r.endswith(version)
            ]
            pr_number = version.split("/")[2]
            if not merge_heads:
                return {
                    "sdk": sdk,
                    "alias": version,
                    "err": f"pull request {pr_number} not found in {sdk_url}",
                }
            sha, _ = merge_heads[0]
            return {
                "sdk": sdk,
                "alias": version,
                "head": True,
                "pr": pr_number,
                "sha": sha,
                "tag": f"pull-{pr_number}",
            }

        remote_tags = [r.split("\t") for r in repo.ls_remote(sdk_url).split("\n")]
        all_listed_tags = [
            (sha, tag.split("refs/tags/")[-1]) for (sha, tag) in remote_tags if "refs/tags/" in tag
        ]

        all_listed_branches = {
            tag.split("refs/heads/")[-1]: sha
            for (sha, tag) in remote_tags
            if tag.startswith("refs/heads/")
        }

        if version in all_listed_branches:
            sha = all_listed_branches[version]
            return {
                "sdk": sdk,
                "alias": version,
                "head": True,
                "sha": sha,
                "tag": version,
            }

        if infix and version.startswith(f"{infix}/"):
            version = version.split(f"{infix}/")[-1]

        listed_tags = all_listed_tags
        if infix:
            listed_tags = [
                (sha, tag.split(f"{infix}/")[-1])
                for (sha, tag) in listed_tags
                if f"{infix}/" in tag
            ]
        semver_regex = r"v?\d+\.\d+\.\d+$"
        listed_tags = [(sha, tag) for (sha, tag) in listed_tags if re.search(semver_regex, tag)]
        listed_tags.sort(key=lambda item: list(map(int, item[1].strip("v").split("."))))
        alias = version
        matching_tags = []
        if version == "latest":
            matching_tags = listed_tags[-1:]
        else:
            if version == "lts":
                version = LTS_VERSIONS[sdk]
            matching_tags = [
                (sha, tag) for (sha, tag) in listed_tags if tag in [version, f"v{version}"]
            ]
        if not matching_tags:
            raise ValueError(f"Tag [{version}] not found in [{sdk_url}]")
        sha, tag = matching_tags[-1]
        release = tag
        if infix:
            release = f"{infix}/{release}"
        return {
            "sdk": sdk,
            "alias": alias,
            "release": release,
            "sha": sha,
            "tag": tag,
        }
    except Exception as e:
        return {
            "sdk": sdk,
            "alias": version,
            "err": f"Error resolving version {version} for {sdk}: {e}",
        }


def main() -> None:
    """CLI entry point for backward-compatible resolve-version.py wrapper."""
    if len(sys.argv) < 3:
        print("Usage: python resolve_version.py <sdk> <tag...>", file=sys.stderr)
        sys.exit(1)

    sdk = sys.argv[1]
    versions = sys.argv[2:]

    if sdk not in SDK_GIT_URLS:
        print(f"Unknown SDK: {sdk}", file=sys.stderr)
        sys.exit(2)
    infix = SDK_TAG_INFIXES.get(sdk)

    results: list[ResolveResult] = []
    shas: set[str] = set()
    for version in versions:
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
