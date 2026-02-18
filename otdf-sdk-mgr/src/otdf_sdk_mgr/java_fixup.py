"""Post-checkout fixups for Java SDK source trees."""

from __future__ import annotations

import re
from pathlib import Path

from otdf_sdk_mgr.config import JAVA_PLATFORM_BRANCH_MAP, get_sdk_dir


def _get_platform_branch(version: str) -> str:
    """Map Java SDK version to compatible platform protocol branch."""
    return JAVA_PLATFORM_BRANCH_MAP.get(version, "main")


def post_checkout_java_fixup(base_dir: Path | None = None) -> None:
    """Fix pom.xml platform.branch property in Java SDK source trees."""
    if base_dir is None:
        base_dir = get_sdk_dir() / "java" / "src"

    if not base_dir.exists():
        print(f"Base directory {base_dir} does not exist, nothing to fix.")
        return

    for src_dir in sorted(base_dir.iterdir()):
        if not src_dir.is_dir() or src_dir.name.endswith(".git"):
            continue

        pom_file = src_dir / "sdk" / "pom.xml"
        if not pom_file.exists():
            print(f"No pom.xml file found in {src_dir}, skipping.")
            continue

        # Extract version from directory name (e.g., "v0.7.5" -> "0.7.5")
        dir_name = src_dir.name
        version = dir_name.lstrip("v")
        platform_branch = _get_platform_branch(version)

        pom_content = pom_file.read_text()

        # Check if the correct platform.branch is already set
        if f"<platform.branch>{platform_branch}</platform.branch>" in pom_content:
            print(f"platform.branch already set to {platform_branch} in {pom_file}, skipping.")
            continue

        # If we don't have a specific mapping (defaults to "main"),
        # check if there's already a valid protocol/go branch set
        if platform_branch == "main":
            match = re.search(r"<platform\.branch>([^<]*)</platform\.branch>", pom_content)
            if match and match.group(1).startswith("protocol/go/"):
                print(
                    f"platform.branch already set to {match.group(1)} in {pom_file} "
                    f"(no mapping for version {version}), skipping."
                )
                continue

        print(f"Updating {pom_file} (version={version}, platform.branch={platform_branch})...")

        if "<platform.branch>" in pom_content:
            # Replace existing platform.branch value
            pom_content = re.sub(
                r"<platform\.branch>[^<]*</platform\.branch>",
                f"<platform.branch>{platform_branch}</platform.branch>",
                pom_content,
            )
            print(f"Updated existing platform.branch to {platform_branch} in {pom_file}")
        elif "<properties>" in pom_content:
            # Add the platform.branch property after <properties>
            pom_content = pom_content.replace(
                "<properties>",
                f"<properties>\n        <platform.branch>{platform_branch}</platform.branch>",
            )
            # Replace hardcoded branch=main with branch=${platform.branch}
            pom_content = pom_content.replace("branch=main", "branch=${platform.branch}")
            print(
                f"Added platform.branch={platform_branch} "
                f"and updated branch references in {pom_file}"
            )
        else:
            # No <properties> section, directly replace branch=main
            pom_content = pom_content.replace("branch=main", f"branch={platform_branch}")
            print(
                f"No <properties> section, directly replaced branch=main "
                f"with branch={platform_branch} in {pom_file}"
            )

        pom_file.write_text(pom_content)

    print("Update complete.")
