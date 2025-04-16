#!/usr/bin/env python3
# Use: python3 resolve-version.py <sdk> <tag...>
#
#    Tag can be:
#       main: the main branch
#       latest: the latest release of the app (last tag)
#       lts: one of a list of hard-coded 'supported' versions
#       <sha>: a git SHA
#       v0.1.2: a git tag that is a semantic version
#       refs/pull/1234: a pull request ref
#
#   The script will resolve the tags to their git SHAs and return it and other metadata in a JSON formatted list of objects.
#   Fields of the object will be:
#     sdk: the SDK name
#     alias: the tag that was requested
#     head: true if the tag is a head of a live branch
#     tag: the resolved tag or branch name, if found
#     sha: the current git SHA of the tag
#     err: an error message if the tag could not be resolved, or resolved to multiple items
#     pr: if set, the pr number associated with the tag
#     release: if set, the release page for the tag
#
#   The script will also check for duplicate SHAs and remove them from the output.
#
# Sample Input:
#
#    python3 resolve-version.py go 0.15.0 latest decaf01 unreleased-name
#
# Sample Output:
# ```json
# [
#   {
#     "sdk": "go",
#     "alias": "0.15.0",
#     "env": "ADDITONAL_OPTION=per build metadata",
#     "release": "v0.15.0",
#     "sha": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0",
#     "tag": "v0.15.0"
#   },
#   {
#     "sdk": "go",
#     "alias": "latest",
#     "release": "v0.15.1",
#     "sha": "c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0a1b2",
#     "tag": "v0.15.1"
#   },
#   {
#     "sdk": "go",
#     "alias": "decaf01",
#     "head": true,
#     "pr": "1234",
#     "sha": "decaf016g7h8i9j0k1l2m3n4o5p6q7r8s9t0a1b2",
#     "tag": "refs/pull/1234/head"
#   },
#   {
#     "sdk": "go",
#     "err": "not found",
#     "tag": "unreleased-name"
#   }
# ]
# ```

import sys
import json
import re
from git import Git
from typing import NotRequired, TypedDict
from urllib.parse import quote


class ResolveSuccess(TypedDict):
    sdk: str  # The SDK name
    alias: str  # The tag that was requested
    env: NotRequired[str]  # Additional options for the SDK
    head: NotRequired[bool]  # True if the tag is a head of a live branch
    pr: NotRequired[str]  # The pull request number associated with the tag
    release: NotRequired[str]  # The release name for the tag
    sha: str  # The current git SHA of the tag
    tag: str  # The resolved tag name


class ResolveError(TypedDict):
    sdk: str  # The SDK name
    alias: str  # The tag that was requested
    err: str  # The error message


ResolveResult = ResolveSuccess | ResolveError

sdk_urls = {
    "go": "https://github.com/opentdf/otdfctl.git",
    "java": "https://github.com/opentdf/java-sdk.git",
    "js": "https://github.com/opentdf/web-sdk.git",
    "platform": "https://github.com/opentdf/platform.git",
}

lts_versions = {
    "go": "0.15.0",
    "java": "0.7.5",
    "js": "0.2.0",
    "platform": "0.4.26",
}


merge_queue_regex = r"^refs/heads/gh-readonly-queue/(?P<branch>[^/]+)/pr-(?P<pr_number>\d+)-(?P<sha>[a-f0-9]{40})$"

sha_regex = r"^[a-f0-9]{7,40}$"


def lookup_additional_options(sdk: str, version: str) -> str | None:
    if sdk != "java":
        return None
    if version.startswith("v"):
        version = version[1:]
    match version:
        case "0.7.8" | "0.7.7":
            return "PLATFORM_BRANCH=protocol/go/v0.2.29"
        case "0.7.6":
            return "PLATFORM_BRANCH=protocol/go/v0.2.25"
        case "0.7.5" | "0.7.4":
            return "PLATFORM_BRANCH=protocol/go/v0.2.18"
        case "0.7.3" | "0.7.2":
            return "PLATFORM_BRANCH=protocol/go/v0.2.17"
        case "0.6.1" | "0.6.0":
            return "PLATFORM_BRANCH=protocol/go/v0.2.14"
        case "0.5.0":
            return "PLATFORM_BRANCH=protocol/go/v0.2.13"
        case "0.4.0" | "0.3.0" | "0.2.0":
            return "PLATFORM_BRANCH=protocol/go/v0.2.10"
        case "0.1.0":
            return "PLATFORM_BRANCH=protocol/go/v0.2.3"
        case _:
            return None


def resolve(sdk: str, version: str, infix: None | str) -> ResolveResult:
    sdk_url = sdk_urls[sdk]
    try:
        repo = Git()
        if version == "main" or version == "refs/heads/main":
            all_heads = [
                r.split("\t") for r in repo.ls_remote(sdk_url, heads=True).split("\n")
            ]
            sha, _ = [tag for tag in all_heads if "refs/heads/main" in tag][0]
            return {
                "sdk": sdk,
                "alias": version,
                "head": True,
                "sha": sha,
                "tag": "main",
            }

        if re.match(sha_regex, version):
            ls_remote = [r.split("\t") for r in repo.ls_remote(sdk_url).split("\n")]
            matching_tags = [
                (sha, tag) for (sha, tag) in ls_remote if sha.startswith(version)
            ]
            if not matching_tags:
                # Not a head; maybe another commit has pushed to this branch since the job started
                return {
                    "sdk": sdk,
                    "alias": version[:7],
                    "sha": version,
                    "tag": version,
                }
            if len(matching_tags) > 1:
                # If multiple tags point to the same SHA, check for pull requests
                # and return the first one.
                for sha, tag in matching_tags:
                    if tag.startswith("refs/pull/"):
                        pr_number = tag.split("/")[-2]
                        return {
                            "sdk": sdk,
                            "alias": version,
                            "head": True,
                            "sha": sha,
                            "tag": f"pull-{pr_number}",
                        }
                # No pull request, probably a feature branch or release branch
                for sha, tag in matching_tags:
                    mq_match = re.match(merge_queue_regex, tag)
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
                    "err": f"SHA {version} points to multiple tags, unable to differentiate: {', '.join(tag for _, tag in matching_tags)}",
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
                r.split("\t")
                for r in repo.ls_remote(sdk_url).split("\n")
                if r.endswith(version)
            ]
            pr_number = version.split("/")[-2]
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

        remote_tags = [
            r.split("\t") for r in repo.ls_remote(sdk_url, tags=True).split("\n")
        ]
        all_listed_tags = [
            (sha, tag.split("refs/tags/")[-1])
            for (sha, tag) in remote_tags
            if "refs/tags/" in tag
        ]

        if version.startswith("refs/tags/"):
            version = version.split("refs/tags/")[-1]
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
        listed_tags = [
            (sha, tag) for (sha, tag) in listed_tags if re.search(semver_regex, tag)
        ]
        listed_tags.sort(key=lambda item: list(map(int, item[1].strip("v").split("."))))
        alias = version
        matching_tags = []
        if version == "latest":
            matching_tags = listed_tags[-1:]
        else:
            if version == "lts":
                version = lts_versions[sdk]
            matching_tags = [
                (sha, tag)
                for (sha, tag) in listed_tags
                if tag in [version, f"v{version}"]
            ]
        if not matching_tags:
            raise ValueError(f"Tag [{version}] not found in [{sdk_url}]")
        sha, tag = matching_tags[-1]
        release = tag
        if infix:
            release = f"{infix}/{release}"
        release = quote(release, safe="-_.~")
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
    if sdk == "platform":
        infix = "service"

    results: list[ResolveResult] = []
    shas: set[str] = set()
    for version in versions:
        v = resolve(sdk, version, infix)
        if "err" not in v:
            env = lookup_additional_options(sdk, version)
            if env:
                v["env"] = env
        if "sha" in v:
            if v["sha"] in shas:
                continue
            shas.add(v["sha"])
        results.append(v)

    print(json.dumps(results))


if __name__ == "__main__":
    main()
