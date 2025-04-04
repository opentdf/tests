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
#       still-supports-<go sdk semver>: For go, get the most recent otdfctl tag that still supports a specific version of the sdk
#
#
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
#     "tag": "v0.15.0",
#     "sha": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"
#   },
#   {
#     "sdk": "go",
#     "alias": "latest",
#     "tag": "v0.15.1",
#     "sha": "c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0a1b2"
#   },
#   {
#     "sdk": "go",
#     "alias": "decaf01",
#     "tag": "refs/pull/1234/head",
#     "sha": "decaf016g7h8i9j0k1l2m3n4o5p6q7r8s9t0a1b2"
#   },
#   {
#     "sdk": "go",
#     "tag": "unreleased-name",
#     "err": "not found"
#   }
# ]
# ```

import json
import re
import sys
import urllib.request

from bisect import bisect_left
from git import Git
from typing import TypedDict
from urllib.parse import quote
from urllib.error import HTTPError, URLError


class ResolveSuccess(TypedDict):
    sdk: str  # The SDK name
    alias: str  # The tag that was requested
    tag: str  # The resolved tag name
    sha: str  # The current git SHA of the tag


class ResolveError(TypedDict):
    sdk: str  # The SDK name
    alias: str  # The tag that was requested
    err: str  # The error message


ResolveResult = ResolveSuccess | ResolveError

sdk_repositories = {
    "go": "opentdf/otdfctl",
    "java": "opentdf/java-sdk",
    "js": "opentdf/web-sdk",
    "platform": "opentdf/platform",
}

sdk_git_urls = {
    sdk: f"https://github.com/{repo}.git" for sdk, repo in sdk_repositories.items()
}

lts_versions = {
    "go": "0.15.0",
    "java": "0.7.5",
    "js": "0.2.0",
    "platform": "0.4.26",
}


sha_regex = r"^[a-f0-9]{7,40}$"
semver_tag_regex = r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$"


def semver_tag_sortkey(semver_tag: str) -> list[int]:
    """
    Convert a semantic version string to a list of integers for sorting.
    """
    return list(map(int, semver_tag.lstrip("v").split(".")))


def get_file_at_tag(sdk: str, branch_or_sha: str, path: str) -> str | None:
    """
    Get the contents of a file at a specific tag in a git repository.
    """
    url = f"https://raw.githubusercontent.com/{sdk_repositories[sdk]}/{quote(branch_or_sha)}/{quote(path)}"
    request = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(request) as response:
            return response.read().decode("utf-8")
    except HTTPError as e:
        raise ValueError(f"Error fetching URL {url}: {e.code} {e.reason}", e)
    except URLError as e:
        raise ValueError(f"Error fetching URL {url}: {e.reason}", e)


def extract_required_version(go_mod_content: str, dependency: str) -> str | None:
    """
    Extract the required version for a specific dependency from a go.mod file.

    Args:
        go_mod_content (str): The contents of the go.mod file.
        dependency (str): The dependency to search for.

    Returns:
        str | None: The required version if found, otherwise None.
    """
    pattern = rf"^\s*{re.escape(dependency)}\s+([\w\.\-]+)"
    for line in go_mod_content.splitlines():
        match = re.match(pattern, line)
        if match:
            return match.group(1)
    return None


def resolve(sdk: str, version: str, infix: None | str) -> ResolveResult:
    sdk_url = sdk_git_urls[sdk]
    try:
        repo = Git()
        if version == "main":
            all_heads = [
                r.split("\t") for r in repo.ls_remote(sdk_url, heads=True).split("\n")
            ]
            sha, _ = [tag for tag in all_heads if "refs/heads/main" in tag][0]
            return {"sdk": sdk, "alias": "main", "tag": "main", "sha": sha}

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
                    "tag": version,
                    "sha": version,
                }
            if len(matching_tags) > 1:
                # If multiple tags point to the same SHA, check for pull requests
                # and return the first one.
                for sha, tag in matching_tags:
                    if tag.startswith("refs/pull/"):
                        return {
                            "sdk": sdk,
                            "alias": version,
                            "tag": tag,
                            "sha": sha,
                        }
                # No pull request, probably a feature branch or release branch
                for sha, tag in matching_tags:
                    if tag.startswith("refs/heads/"):
                        return {
                            "sdk": sdk,
                            "alias": version,
                            "tag": tag.split("refs/heads/")[-1],
                            "sha": sha,
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
                "tag": tag,
                "sha": sha,
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
                "tag": f"pull-{pr_number}",
                "sha": sha,
            }

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
        # Strip all tags that are not semver tags (requires a v prefix, must be 3 parts, no build or prerelease info)
        listed_tags = [
            (sha, tag) for (sha, tag) in listed_tags if re.search(semver_tag_regex, tag)
        ]
        listed_tags.sort(key=lambda item: semver_tag_sortkey(item[1]))
        alias = version
        if version == "latest":
            sha, tag = listed_tags[-1]
            return {"sdk": sdk, "alias": alias, "tag": tag, "sha": sha}
        if version.startswith("still-supports-"):
            target_version = version.split("-")[-1]
            if not re.match(semver_tag_regex, target_version):
                raise ValueError(f"Invalid still-supports version: [{target_version}]")

            # Find the most recent tag that is less than or equal to the given SHA
            def tagpair_to_depversion(tagpair: tuple[str, str]) -> list[int]:
                sha, tag = tagpair
                gomod_file = get_file_at_tag("go", sha, "go.mod")
                if not gomod_file:
                    raise ValueError(
                        f"Error fetching go.mod for SHA {sha}, at tag [{tag}]"
                    )
                vsdk = extract_required_version(
                    gomod_file, "github.com/opentdf/platform/sdk"
                )
                if not vsdk:
                    raise ValueError(
                        f"Error extracting version for SHA {sha}, at tag [{tag}]"
                    )
                return semver_tag_sortkey(vsdk)

            index = bisect_left(
                listed_tags,
                semver_tag_sortkey(target_version),
                key=tagpair_to_depversion,
            )
            if index == 0:
                raise ValueError(f"No tags found before SHA {version}")
            sha, tag = listed_tags[index - 1]
            return {"sdk": sdk, "alias": alias, "tag": tag, "sha": sha}
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
            sha, tag = matching_tags[0]
            return {"sdk": sdk, "alias": alias, "tag": tag, "sha": sha}
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

    if sdk not in sdk_git_urls:
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
