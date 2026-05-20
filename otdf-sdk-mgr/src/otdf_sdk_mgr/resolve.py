"""Version resolution for SDK tags/branches/SHAs."""

from __future__ import annotations

import re
from typing import NotRequired, TypedDict, TypeGuard

import git.exc
from git import Git

from otdf_sdk_mgr.config import (
    JAVA_PLATFORM_BRANCH_MAP,
    LTS_VERSIONS,
    SDK_GIT_URLS,
    SDK_NPM_PACKAGES,
    SDK_TAG_INFIXES_PLATFORM_GO,
)


class ResolveSuccess(TypedDict):
    sdk: str
    alias: str
    env: NotRequired[str]
    head: NotRequired[bool]
    pr: NotRequired[str]
    release: NotRequired[str]
    sha: str
    source: NotRequired[str]
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

SHA_REGEX = r"^[a-f0-9]{7,64}$"

# otdfctl moved into the platform monorepo at v0.31.0. Tags below this cannot be
# source-built from the platform checkout (the otdfctl/ subdir doesn't exist at
# those commits) and are resolved against the archived standalone repo for
# artifact install only.
OTDFCTL_PLATFORM_MIN_VERSION = (0, 31, 0)


def _try_resolve_js_npm(
    sdk: str,
    version: str,
    alias: str,
    infix_stripped_tags: list[tuple[str, str]],
    infix: str | None,
) -> ResolveSuccess | None:
    """Try to resolve a JS version from the npm registry.

    Returns a ResolveSuccess if the version exists on npm, None otherwise.
    The sha is populated from git tags on a best-effort basis (empty string if not found),
    since it is only needed for source checkouts which are skipped for artifact installs.
    """
    from otdf_sdk_mgr.registry import fetch_json

    package = SDK_NPM_PACKAGES.get(sdk)
    if not package:
        return None

    npm_version = version.lstrip("v")
    try:
        data = fetch_json(f"https://registry.npmjs.org/{package}/{npm_version}")
    except Exception:
        return None

    # npm may resolve a dist-tag (e.g. "next") to a concrete version
    resolved_version = data.get("version", npm_version)
    tag = resolved_version

    # Look up SHA from git tags (best-effort; not required for artifact installs)
    sha = ""
    candidates = {resolved_version, f"v{resolved_version}"}
    for s, t in infix_stripped_tags:
        if t in candidates:
            sha = s
            break

    release = f"{infix}/{tag}" if infix else tag
    return {
        "sdk": sdk,
        "alias": alias,
        "release": release,
        "sha": sha,
        "tag": tag,
    }


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


def _semver_tuple(version: str) -> tuple[int, int, int] | None:
    """Parse 'vX.Y.Z' or 'X.Y.Z' into a tuple; ignore pre-release/build suffixes."""
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", version)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def go_source_for(version: str) -> str:
    """Decide whether a go version resolves against platform or standalone.

    Heads, SHAs, branch names, "main", "latest" → platform. Semver tags →
    platform for v0.31.0+ (where otdfctl/ lives in the monorepo), else
    standalone (artifact-install fallback for archived releases).
    "lts" follows LTS_VERSIONS["go"].
    """
    if version in ("main", "latest"):
        return "platform"
    if re.match(SHA_REGEX, version):
        return "platform"
    if version.startswith("refs/"):
        return "platform"
    if version == "lts":
        lts_semver = _semver_tuple(LTS_VERSIONS.get("go", ""))
        if lts_semver is not None and lts_semver < OTDFCTL_PLATFORM_MIN_VERSION:
            return "standalone"
        return "platform"
    bare = version.removeprefix("otdfctl/")
    semver = _semver_tuple(bare)
    if semver is not None and semver < OTDFCTL_PLATFORM_MIN_VERSION:
        return "standalone"
    return "platform"


def _looks_like_release_tag(version: str) -> bool:
    """Whether `version` could be a release tag (for standalone fallback)."""
    bare = version.removeprefix("otdfctl/")
    return _semver_tuple(bare) is not None or version == "lts"


def resolve(
    sdk: str,
    version: str,
    infix: str | None,
) -> ResolveResult:
    """Resolve a version spec to a concrete SHA and tag.

    For sdk='go', resolution always targets the platform monorepo's otdfctl/
    subtree (tags `otdfctl/vX.Y.Z`, infix `otdfctl`). Pre-v0.31.0 tags fall
    back to the archived standalone opentdf/otdfctl repo and are flagged
    artifact-install-only via source="standalone".

    Args:
        sdk: SDK identifier (go, js, java, platform).
        version: Version spec (main, SHA, tag, latest, lts, etc.).
        infix: Tag infix for monorepo tag resolution (e.g. "sdk" for JS).
            Ignored for sdk='go' (always overridden to "otdfctl" or None
            depending on the resolved source).
    """
    if sdk == "go":
        go_source = go_source_for(version)
        if go_source == "platform":
            sdk_url = SDK_GIT_URLS["platform"]
            go_infix: str | None = SDK_TAG_INFIXES_PLATFORM_GO
        else:
            sdk_url = SDK_GIT_URLS["go"]
            go_infix = None
        result = _resolve_against(sdk, version, go_infix, sdk_url)
        if is_resolve_success(result):
            result["source"] = go_source
            return result
        # Platform miss on a tag-like input: try the archived standalone repo.
        if go_source == "platform" and _looks_like_release_tag(version):
            fallback = _resolve_against(sdk, version, None, SDK_GIT_URLS["go"])
            if is_resolve_success(fallback):
                fallback["source"] = "standalone"
                return fallback
        return result

    try:
        sdk_url = SDK_GIT_URLS[sdk]
    except KeyError:
        return {"sdk": sdk, "alias": version, "err": f"unknown SDK: {sdk}"}
    return _resolve_against(sdk, version, infix, sdk_url)


def _resolve_against(
    sdk: str,
    version: str,
    infix: str | None,
    sdk_url: str,
) -> ResolveResult:
    """Run ls-remote-based resolution against a specific git URL."""
    try:
        repo = Git()
        version = version.removeprefix("refs/heads/")
        if version == "main":
            all_heads = [r.split("\t") for r in repo.ls_remote(sdk_url, heads=True).split("\n")]
            try:
                sha, _ = next(tag for tag in all_heads if "refs/heads/main" in tag)
            except StopIteration:
                return {"sdk": sdk, "alias": version, "err": f"main branch not found in {sdk_url}"}
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

        # For JS: explicit version refs resolve via npm first so that pre-release and
        # dist-tag refs (e.g. "0.9.0-beta.84", "next") work without a matching git tag.
        if sdk in SDK_NPM_PACKAGES and version not in ("latest", "lts"):
            npm_result = _try_resolve_js_npm(sdk, version, version, listed_tags, infix)
            if npm_result is not None:
                return npm_result

        semver_regex = r"v?\d+\.\d+\.\d+$"
        stable_tags = [(sha, tag) for (sha, tag) in listed_tags if re.search(semver_regex, tag)]
        stable_tags.sort(key=lambda item: list(map(int, item[1].strip("v").split("."))))
        alias = version
        matching_tags = []
        if version == "latest":
            # For Java, check if CLI artifacts are available and fall back to source build if not
            if sdk == "java":
                from otdf_sdk_mgr.registry import list_java_github_releases

                gh_releases = list_java_github_releases()
                # Find the latest version with CLI artifact
                versions_with_cli = [r for r in gh_releases if r.get("has_cli", False)]
                if versions_with_cli:
                    # Use the latest version that has CLI
                    latest_with_cli_tag = versions_with_cli[-1]["version"]
                    matching_tags = [
                        (sha, tag)
                        for (sha, tag) in stable_tags
                        if tag in [latest_with_cli_tag, latest_with_cli_tag.lstrip("v")]
                    ]
                if not matching_tags:
                    # No versions with CLI found, fall back to building latest from source
                    sha, tag = stable_tags[-1]
                    return {
                        "sdk": sdk,
                        "alias": alias,
                        "head": True,  # Mark as head to trigger source checkout
                        "sha": sha,
                        "tag": tag,
                    }
            else:
                matching_tags = stable_tags[-1:]
        else:
            if version == "lts":
                if sdk not in LTS_VERSIONS:
                    raise ValueError(
                        f"No LTS version defined for SDK '{sdk}'. "
                        f"Add it to LTS_VERSIONS in config.py."
                    )
                version = LTS_VERSIONS[sdk]
            matching_tags = [
                (sha, tag) for (sha, tag) in stable_tags if tag in [version, f"v{version}"]
            ]
            # If not found in stable tags, also search all tags (supports pre-release versions)
            if not matching_tags:
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
    except (git.exc.GitCommandError, ValueError) as e:
        return {
            "sdk": sdk,
            "alias": version,
            "err": f"Error resolving version {version} for {sdk}: {e}",
        }
