#!/usr/bin/env python3

import sys
import json
import re

from git import Git
from typing import TypedDict


class ResolveSuccess(TypedDict):
    sdk: str
    tag: str
    sha: str


class ResolveError(TypedDict):
    sdk_name: str
    err: str


ResolveResult = ResolveSuccess | ResolveError

sdk_urls = {
    "go": "https://github.com/opentdf/otdfctl.git",
    "java": "https://github.com/opentdf/java-sdk.git",
    "js": "https://github.com/opentdf/web-sdk.git",
}


def resolve(sdk: str, version: str, infix: None | str) -> ResolveResult:
    sdk_url = sdk_urls[sdk]
    try:
        repo = Git()
        if version == "main":
            all_heads = [
                r.split("\t") for r in repo.ls_remote(sdk_url, heads=True).split("\n")
            ]
            sha, _ = [tag for tag in all_heads if "refs/heads/main" in tag][0]
            return {"sdk": sdk, "tag": "main", "sha": sha}

        remote_tags = [
            r.split("\t") for r in repo.ls_remote(sdk_url, tags=True).split("\n")
        ]
        all_listed_tags = [
            (sha, tag.split("refs/tags/")[-1])
            for (sha, tag) in remote_tags
            if "refs/tags/" in tag
        ]
        listed_tags = all_listed_tags
        if infix:
            listed_tags = [
                (sha, tag.split(f"{infix}/")[-1])
                for (sha, tag) in listed_tags
                if f"{infix}/" in tag
            ]
        semver_regex = r"v?\d+\.\d+\.\d+$"
        listed_tags = [
            (sha, tag) for (sha, tag) in listed_tags if re.search(semver_regex, tag)
        ]
        listed_tags.sort(key=lambda item: list(map(int, item[1].strip("v").split("."))))
        if version == "latest":
            sha, tag = listed_tags[-1]
            return {"sdk": sdk, "tag": tag, "sha": sha}
        else:
            matching_tags = [
                (sha, tag)
                for (sha, tag) in listed_tags
                if tag in [version, f"v{version}"]
            ]
            if not matching_tags:
                raise ValueError(f"Tag [{version}] not found in [{sdk_url}]")
            sha, tag = matching_tags[0]
            return {"sdk": sdk, "tag": tag, "sha": sha}
    except Exception as e:
        return {
            "sdk_name": sdk,
            "err": f"Error resolving version {version} for {sdk}: {e}",
        }


def main():
    if len(sys.argv) < 3:
        print("Usage: python resolve_version.py <sdk> <tag...>", file=sys.stderr)
        sys.exit(1)

    sdk = sys.argv[1]
    versions = sys.argv[2:]

    if sdk not in sdk_urls:
        print(f"Unknown SDK: {sdk}", file=sys.stderr)
        sys.exit(2)
    infix: None | str = None
    if sdk == "js":
        infix = "sdk"

    results: list[ResolveResult] = []
    shas: set[str] = set()
    for version in versions:
        v = resolve(sdk, version, infix)
        if "sha" in v:
            if v["sha"] in shas:
                continue
            shas.add(v["sha"])
        results.append(v)

    print(json.dumps(results))
    if any("err" in r for r in results):
        sys.exit(3)


if __name__ == "__main__":
    main()
