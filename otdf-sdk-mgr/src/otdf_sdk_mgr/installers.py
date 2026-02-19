"""SDK CLI installation functions."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from otdf_sdk_mgr.config import (
    LTS_VERSIONS,
    get_sdk_dir,
    get_sdk_dirs,
)
from otdf_sdk_mgr.checkout import checkout_sdk_branch
from otdf_sdk_mgr.registry import list_go_versions, list_java_github_releases, list_js_versions
from otdf_sdk_mgr.semver import normalize_version


class InstallError(Exception):
    """Raised when SDK installation fails."""


def install_go_release(version: str, dist_dir: Path) -> None:
    """Install a Go CLI release by writing a .version file.

    The cli.sh and otdfctl.sh wrappers read .version and use
    `go run github.com/opentdf/otdfctl@{version}` instead of a local binary.
    """
    go_dir = get_sdk_dir() / "go"
    dist_dir.mkdir(parents=True, exist_ok=True)
    tag = normalize_version(version)
    (dist_dir / ".version").write_text(f"{tag}\n")
    shutil.copy(go_dir / "cli.sh", dist_dir / "cli.sh")
    shutil.copy(go_dir / "otdfctl.sh", dist_dir / "otdfctl.sh")
    shutil.copy(go_dir / "opentdfctl.yaml", dist_dir / "opentdfctl.yaml")
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
    js_dir = get_sdk_dir() / "js"
    dist_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(js_dir / "cli.sh", dist_dir / "cli.sh")
    # Strip infix prefix (e.g., "sdk/v0.4.0" -> "v0.4.0") for npm install
    v = version.split("/")[-1].lstrip("v")
    print(f"  Installing @opentdf/ctl@{v} from npm...")
    subprocess.check_call(
        ["npm", "install", f"@opentdf/ctl@{v}"],
        cwd=dist_dir,
    )
    print(f"  JS release {v} installed to {dist_dir}")


def install_java_release(version: str, dist_dir: Path) -> None:
    """Install a Java CLI release by downloading cmdline.jar from GitHub Releases.

    Raises InstallError if the artifact is not available or download fails,
    so the caller can fall back to building from source.
    """
    java_dir = get_sdk_dir() / "java"
    tag = normalize_version(version)
    url = f"https://github.com/opentdf/java-sdk/releases/download/{tag}/cmdline.jar"

    # Check if artifact exists before trying to download
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=10):
            pass
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise InstallError(
                f"cmdline.jar not found for {tag}. "
                f"The release {tag} does not include a CLI artifact. "
                f"This version will need to be built from source. "
                f"Check: https://github.com/opentdf/java-sdk/releases/tag/{tag}"
            )
        raise
    except (urllib.error.URLError, OSError) as e:
        print(f"  Warning: Could not verify artifact availability: {e}", file=sys.stderr)
        # Proceed with download attempt anyway

    # Download to a temp file first to avoid partial writes
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jar") as tmp:
            tmp_path = Path(tmp.name)
        print(f"  Downloading cmdline.jar from {url}...")
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                with open(tmp_path, "wb") as f:
                    shutil.copyfileobj(response, f)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise InstallError(
                    f"cmdline.jar not found for {tag} (race condition?). "
                    f"Check: https://github.com/opentdf/java-sdk/releases/tag/{tag}"
                )
            raise

        # Download succeeded — now create dist_dir and move files into place
        dist_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(java_dir / "cli.sh", dist_dir / "cli.sh")
        shutil.move(str(tmp_path), str(dist_dir / "cmdline.jar"))
        tmp_path = None  # Ownership transferred; don't clean up
    except BaseException:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        if dist_dir.exists() and not (dist_dir / "cmdline.jar").exists():
            shutil.rmtree(dist_dir, ignore_errors=True)
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

    Raises:
        InstallError: If the SDK is unknown or installation fails.
    """
    if sdk not in INSTALLERS:
        raise InstallError(f"Unknown SDK '{sdk}'. Must be one of: {', '.join(INSTALLERS)}")

    sdk_dirs = get_sdk_dirs()
    name = dist_name or normalize_version(version)
    dist_dir = sdk_dirs[sdk] / "dist" / name
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
    sdk_dirs = get_sdk_dirs()
    for sdk in sdks:
        print(f"Checking out and building {sdk} from source...")
        checkout_sdk_branch(sdk, "main")
        make_dir = sdk_dirs[sdk]
        subprocess.check_call(["make"], cwd=make_dir)
        print(f"  {sdk} built from source")


def cmd_release(specs: list[str]) -> None:
    """Install specific released versions from sdk:version specs."""
    for spec in specs:
        if ":" not in spec:
            raise InstallError(f"Invalid spec '{spec}'. Use format sdk:version (e.g., go:v0.24.0)")
        sdk, version = spec.split(":", 1)
        print(f"Installing {sdk} {version} from registry...")
        install_release(sdk, version)


def cmd_install(sdk: str, version: str, dist_name: str | None = None) -> None:
    """Install a single SDK version (used by CI action)."""
    print(f"Installing {sdk} {version}...")
    install_release(sdk, version, dist_name=dist_name)
