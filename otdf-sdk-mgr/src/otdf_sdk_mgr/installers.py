"""SDK CLI installation functions."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from otdf_sdk_mgr.config import (
    ALL_SDKS,
    GO_DIR,
    JAVA_DIR,
    JS_DIR,
    LTS_VERSIONS,
    SDK_DIRS,
    SCRIPTS_DIR,
)
from otdf_sdk_mgr.registry import list_go_versions, list_java_github_releases, list_js_versions
from otdf_sdk_mgr.semver import normalize_version


def install_go_release(version: str, dist_dir: Path) -> None:
    """Install a Go CLI release by writing a .version file.

    The cli.sh and otdfctl.sh wrappers read .version and use
    `go run github.com/opentdf/otdfctl@{version}` instead of a local binary.
    """
    dist_dir.mkdir(parents=True, exist_ok=True)
    tag = normalize_version(version)
    (dist_dir / ".version").write_text(f"{tag}\n")
    shutil.copy(GO_DIR / "cli.sh", dist_dir / "cli.sh")
    shutil.copy(GO_DIR / "otdfctl.sh", dist_dir / "otdfctl.sh")
    shutil.copy(GO_DIR / "opentdfctl.yaml", dist_dir / "opentdfctl.yaml")
    print(f"  Pre-warming Go cache for otdfctl@{tag}...")
    result = subprocess.run(
        ["go", "install", f"github.com/opentdf/otdfctl@{tag}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"  Warning: go install pre-warm failed (will retry at runtime): {result.stderr.strip()}"
        )
    print(f"  Go release {tag} installed to {dist_dir}")


def install_js_release(version: str, dist_dir: Path) -> None:
    """Install a JS CLI release from npm registry."""
    dist_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(JS_DIR / "cli.sh", dist_dir / "cli.sh")
    v = version.lstrip("v")
    print(f"  Installing @opentdf/ctl@{v} from npm...")
    subprocess.check_call(
        ["npm", "install", f"@opentdf/ctl@{v}"],
        cwd=dist_dir,
    )
    print(f"  JS release {v} installed to {dist_dir}")


def install_java_release(version: str, dist_dir: Path) -> None:
    """Install a Java CLI release by downloading cmdline.jar from GitHub Releases."""
    dist_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(JAVA_DIR / "cli.sh", dist_dir / "cli.sh")
    tag = normalize_version(version)
    url = f"https://github.com/opentdf/java-sdk/releases/download/{tag}/cmdline.jar"
    jar_path = dist_dir / "cmdline.jar"
    print(f"  Downloading cmdline.jar from {url}...")
    try:
        urllib.request.urlretrieve(url, jar_path)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  Error: cmdline.jar not found for {tag}.", file=sys.stderr)
            print(f"  The release {tag} may not include a CLI artifact.", file=sys.stderr)
            print(
                f"  Check: https://github.com/opentdf/java-sdk/releases/tag/{tag}",
                file=sys.stderr,
            )
            sys.exit(1)
        raise
    print(f"  Java release {tag} installed to {dist_dir}")


INSTALLERS = {
    "go": install_go_release,
    "js": install_js_release,
    "java": install_java_release,
}


def install_release(sdk: str, version: str, dist_name: str | None = None) -> Path:
    """Install a released version of an SDK CLI.

    Args:
        sdk: One of "go", "js", "java"
        version: Version string (e.g., "v0.24.0" or "0.24.0")
        dist_name: Override the dist directory name (defaults to normalized version)

    Returns:
        Path to the created dist directory
    """
    if sdk not in INSTALLERS:
        print(
            f"Error: Unknown SDK '{sdk}'. Must be one of: {', '.join(INSTALLERS)}",
            file=sys.stderr,
        )
        sys.exit(1)

    name = dist_name or normalize_version(version)
    dist_dir = SDK_DIRS[sdk] / "dist" / name
    if dist_dir.exists():
        print(f"  Dist directory already exists: {dist_dir} (skipping)")
        return dist_dir

    INSTALLERS[sdk](version, dist_dir)
    return dist_dir


def latest_stable_version(sdk: str) -> str | None:
    """Find the latest stable version for an SDK that has a CLI available."""
    if sdk == "go":
        versions = list_go_versions()
        stable = [v for v in versions if v.get("stable", False)]
        return stable[-1]["version"] if stable else None
    elif sdk == "js":
        versions = list_js_versions()
        stable = [v for v in versions if v.get("stable", False)]
        return stable[-1]["version"] if stable else None
    elif sdk == "java":
        releases = list_java_github_releases()
        stable_with_cli = [
            v for v in releases if v.get("stable", False) and v.get("has_cli", False)
        ]
        return stable_with_cli[-1]["version"] if stable_with_cli else None
    return None


def cmd_stable(sdks: list[str]) -> None:
    """Install the latest stable release for each SDK."""
    for sdk in sdks:
        print(f"Finding latest stable {sdk} release...")
        version = latest_stable_version(sdk)
        if version is None:
            print(f"  Warning: No stable version found for {sdk}, skipping")
            continue
        print(f"  Latest stable {sdk}: {version}")
        install_release(sdk, version)


def cmd_lts(sdks: list[str]) -> None:
    """Install LTS versions for each SDK."""
    for sdk in sdks:
        version = LTS_VERSIONS.get(sdk)
        if version is None:
            print(f"  Warning: No LTS version defined for {sdk}, skipping")
            continue
        print(f"Installing LTS {sdk} {version}...")
        install_release(sdk, version)


def cmd_tip(sdks: list[str]) -> None:
    """Delegate to source checkout + make for head builds."""
    for sdk in sdks:
        print(f"Checking out and building {sdk} from source...")
        checkout_script = SCRIPTS_DIR / "checkout-sdk-branch.sh"
        subprocess.check_call([str(checkout_script), sdk, "main"])
        make_dir = SDK_DIRS[sdk]
        subprocess.check_call(["make"], cwd=make_dir)
        print(f"  {sdk} built from source")


def cmd_release(specs: list[str]) -> None:
    """Install specific released versions from sdk:version specs."""
    for spec in specs:
        if ":" not in spec:
            print(
                f"Error: Invalid spec '{spec}'. Use format sdk:version (e.g., go:v0.24.0)",
                file=sys.stderr,
            )
            sys.exit(1)
        sdk, version = spec.split(":", 1)
        print(f"Installing {sdk} {version} from registry...")
        install_release(sdk, version)


def cmd_install(sdk: str, version: str, dist_name: str | None = None) -> None:
    """Install a single SDK version (used by CI action)."""
    print(f"Installing {sdk} {version}...")
    install_release(sdk, version, dist_name=dist_name)


def configure_main() -> None:
    """Backward-compatible argparse CLI entry point for scripts/configure.py wrapper."""
    parser = argparse.ArgumentParser(
        description="Configure SDK artifacts for xtest.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_stable = subparsers.add_parser("stable", help="Install latest stable releases")
    p_stable.add_argument(
        "sdks", nargs="*", default=ALL_SDKS, help="SDKs to install (default: all)"
    )

    p_lts = subparsers.add_parser("lts", help="Install LTS versions")
    p_lts.add_argument("sdks", nargs="*", default=ALL_SDKS, help="SDKs to install (default: all)")

    p_tip = subparsers.add_parser("tip", help="Source checkout + build from main")
    p_tip.add_argument("sdks", nargs="*", default=ALL_SDKS, help="SDKs to build (default: all)")

    p_release = subparsers.add_parser("release", help="Install specific released versions")
    p_release.add_argument(
        "specs",
        nargs="+",
        metavar="SDK:VERSION",
        help="Version specs (e.g., go:v0.24.0 js:0.4.0 java:v0.9.0)",
    )

    p_install = subparsers.add_parser("install", help="Install a single SDK version (CI)")
    p_install.add_argument("--sdk", required=True, choices=ALL_SDKS)
    p_install.add_argument("--version", required=True, help="Version to install")
    p_install.add_argument("--dist-name", default=None, help="Override dist directory name")

    args = parser.parse_args()

    if args.command == "stable":
        cmd_stable(args.sdks)
    elif args.command == "lts":
        cmd_lts(args.sdks)
    elif args.command == "tip":
        cmd_tip(args.sdks)
    elif args.command == "release":
        cmd_release(args.specs)
    elif args.command == "install":
        cmd_install(args.sdk, args.version, dist_name=args.dist_name)
