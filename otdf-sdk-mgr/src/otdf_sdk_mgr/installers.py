"""SDK CLI installation functions."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from otdf_sdk_mgr.checkout import checkout_sdk_branch
from otdf_sdk_mgr.config import (
    GO_MODULE_PATH_PLATFORM,
    LTS_VERSIONS,
    SDK_GIT_URLS,
    SDK_MAVEN_COORDS,
    get_sdk_dir,
    get_sdk_dirs,
    go_module_for_tag,
)
from otdf_sdk_mgr.registry import list_go_versions, list_java_github_releases, list_js_versions
from otdf_sdk_mgr.semver import normalize_version


class InstallError(Exception):
    """Raised when SDK installation fails."""


def install_go_release(version: str, dist_dir: Path) -> None:
    """Install a Go CLI release by writing a .version file.

    The cli.sh and otdfctl.sh wrappers read .version and use
    `go run <module>@{version}` instead of a local binary. The .version file
    contains `module-path@version` (e.g., `github.com/opentdf/platform/otdfctl@v0.31.0`).
    Pre-v0.31.0 tags use the archived `github.com/opentdf/otdfctl` module path.

    `go install` is run first to surface module-resolution failures eagerly;
    only after it succeeds do we lay down `.version` + cli wrappers, so a
    failed install never leaves a directory that looks successful to the
    `dist_dir.exists()` skip check in `install_release`.
    """
    go_dir = get_sdk_dir() / "go"
    # Strip tag infix (e.g., "otdfctl/v0.24.0" → "v0.24.0")
    if "/" in version:
        version = version.rsplit("/", 1)[-1]
    tag = normalize_version(version)
    module = go_module_for_tag(tag)
    print(f"  Pre-warming Go cache for {module}@{tag}...")
    result = subprocess.run(
        ["go", "install", f"{module}@{tag}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        msg = f"go install failed for {module}@{tag}: {result.stderr.strip()}"
        if module == GO_MODULE_PATH_PLATFORM:
            raise InstallError(
                f"{msg}\nThe platform module path {module}@{tag} may not be published yet."
            )
        raise InstallError(msg)
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / ".version").write_text(f"{module}@{tag}\n")
    shutil.copy(go_dir / "cli.sh", dist_dir / "cli.sh")
    shutil.copy(go_dir / "otdfctl.sh", dist_dir / "otdfctl.sh")
    shutil.copy(go_dir / "opentdfctl.yaml", dist_dir / "opentdfctl.yaml")
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
    """Install a Java CLI release.

    Prefers a prebuilt cmdline.jar from GitHub Releases. Failing that, builds
    only the cmdline module of the release tag against the sdk jars published
    to Maven Central, which skips the sdk module's `buf generate` codegen (and
    its buf.build rate limits) entirely.

    Raises InstallError if neither works, so CI (xtest/setup-cli-tool) can
    fall back to a full source build.
    """
    tag = normalize_version(version)
    try:
        _download_java_github_release(tag, dist_dir)
    except InstallError as download_err:
        print(f"  {download_err}", file=sys.stderr)
        print(f"  Building the {tag} CLI against the sdk published to Maven Central...")
        try:
            _build_java_cli_against_maven_central(tag, dist_dir)
        except InstallError as build_err:
            raise InstallError(
                f"No usable GitHub cmdline.jar for {tag} ({download_err}); "
                f"Maven Central build failed ({build_err})"
            ) from build_err


def _download_java_github_release(tag: str, dist_dir: Path) -> None:
    """Download cmdline.jar from a java-sdk GitHub Release into dist_dir."""
    java_dir = get_sdk_dir() / "java"
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
                f"Check: https://github.com/opentdf/java-sdk/releases/tag/{tag}"
            )
        raise InstallError(f"Could not check GitHub for {tag} cmdline.jar: {e}") from e
    except OSError as e:
        print(f"  Warning: Could not verify artifact availability: {e}", file=sys.stderr)
        # Proceed with download attempt anyway

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jar") as tmp:
            tmp_path = Path(tmp.name)
        print(f"  Downloading cmdline.jar from {url}...")
        try:
            with urllib.request.urlopen(url, timeout=60) as response, open(tmp_path, "wb") as f:
                shutil.copyfileobj(response, f)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise InstallError(
                    f"cmdline.jar not found for {tag} (race condition?). "
                    f"Check: https://github.com/opentdf/java-sdk/releases/tag/{tag}"
                )
            raise InstallError(f"Downloading {tag} cmdline.jar failed: {e}") from e
        except OSError as e:
            raise InstallError(f"Downloading {tag} cmdline.jar failed: {e}") from e

        dist_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(java_dir / "cli.sh", dist_dir / "cli.sh")
        shutil.move(str(tmp_path), str(dist_dir / "cmdline.jar"))
        tmp_path = None
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        if dist_dir.exists() and not (dist_dir / "cmdline.jar").exists():
            shutil.rmtree(dist_dir, ignore_errors=True)

    print(f"  Java release {tag} installed to {dist_dir}")


# Local Maven repository for release CLI builds; see _build_java_cli_against_maven_central.
JAVA_RELEASE_MAVEN_REPO = Path.home() / ".m2" / "otdf-sdk-mgr-releases"


def _java_sdk_on_maven_central(tag: str) -> bool:
    """Whether io.opentdf.platform:sdk is published to Maven Central at `tag`."""
    v = tag.removeprefix("v")
    url = f"{SDK_MAVEN_COORDS['java']['base_url']}/{v}/sdk-{v}.pom"
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=10):
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise InstallError(f"Could not check Maven Central for sdk {v}: {e}") from e
    except OSError as e:
        raise InstallError(f"Could not reach Maven Central to check for sdk {v}: {e}") from e


def _build_java_cli_against_maven_central(tag: str, dist_dir: Path) -> None:
    """Build cmdline.jar from the `tag` checkout, resolving sdk* from Maven Central.

    `-pl .,cmdline` builds just the parent pom (the enforcer's reactor
    convergence rule needs it) and the CLI, so the sdk module's codegen never
    runs. The checkout lives in a temp dir, not under src/, so the java
    Makefile won't pick it up for a second, full build.

    Maven uses its own local repository: java-sdk branches carry the version
    of the last release, so a head that was `mvn install`ed into ~/.m2 would
    otherwise shadow the published sdk jars this build is meant to use.
    """
    if not _java_sdk_on_maven_central(tag):
        raise InstallError(f"io.opentdf.platform:sdk {tag} is not published to Maven Central")
    java_dir = get_sdk_dir() / "java"
    with tempfile.TemporaryDirectory(prefix=f"java-sdk-{tag}-") as tmp:
        src_dir = Path(tmp) / "java-sdk"
        cmds = [
            [
                "git",
                "clone",
                "--quiet",
                "--depth=1",
                f"--branch={tag}",
                SDK_GIT_URLS["java"],
                str(src_dir),
            ],
            [
                "mvn",
                "--batch-mode",
                "--file",
                str(src_dir / "pom.xml"),
                "--projects",
                ".,cmdline",
                f"-Dmaven.repo.local={JAVA_RELEASE_MAVEN_REPO}",
                "package",
                "-DskipTests",
                "-Dmaven.javadoc.skip=true",
            ],
        ]
        for cmd in cmds:
            try:
                subprocess.check_call(cmd)
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                raise InstallError(f"Running {cmd[0]} for the {tag} CLI failed: {e}") from e
        jar = src_dir / "cmdline" / "target" / "cmdline.jar"
        if not jar.is_file():
            raise InstallError(f"Built the {tag} CLI but {jar} is missing")
        try:
            dist_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(java_dir / "cli.sh", dist_dir / "cli.sh")
            shutil.copy(jar, dist_dir / "cmdline.jar")
        except OSError as e:
            # A partial dist_dir would be skipped as "already installed" next time.
            shutil.rmtree(dist_dir, ignore_errors=True)
            raise InstallError(
                f"Built the {tag} CLI but could not install it to {dist_dir}: {e}"
            ) from e
    print(f"  Java release {tag} built against Maven Central and installed to {dist_dir}")


INSTALLERS = {
    "go": install_go_release,
    "js": install_js_release,
    "java": install_java_release,
}


def install_release(sdk: str, version: str, dist_name: str | None = None) -> Path:
    """Install a released version of an SDK CLI.

    Raises InstallError if the SDK is unknown or installation fails.
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
    """Find the latest stable release version for an SDK."""
    if sdk == "go":
        stable = [v for v in list_go_versions() if v.get("stable", False)]
        return stable[-1]["version"] if stable else None
    elif sdk == "js":
        stable = [v for v in list_js_versions() if v.get("stable", False)]
        return stable[-1]["version"] if stable else None
    elif sdk == "java":
        # No has_cli filter: install_java_release builds the CLI against Maven
        # Central when a release has no cmdline.jar asset (and fails, for a CI
        # source build, if the sdk isn't published there). The GitHub listing is
        # only needed for its prerelease flag.
        stable = [v for v in list_java_github_releases() if v.get("stable", False)]
        return stable[-1]["version"] if stable else None
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


def cmd_tip(sdks: list[str], ref: str = "main") -> None:
    """Delegate to source checkout + make for source builds at `ref`.

    `ref` defaults to `main` to preserve historical behavior. May be a branch,
    tag, SHA, `pr:N` shorthand, or raw `refs/...`. The slug derived from the
    ref is passed to `make` via `VERSIONS=<slug>` so only that checkout is
    (re)built, not every directory under `sdk/<lang>/src/`.
    """
    import os

    from otdf_sdk_mgr.checkout import checkout_go_from_platform
    from otdf_sdk_mgr.refs import expand_pr_shorthand

    expanded = expand_pr_shorthand(ref)
    # Slug for SDK src/<slug> and dist/<slug> — mirrors the per-SDK
    # `local_name` calculation in checkout.py.
    slug = expanded.replace("/", "--").removeprefix("sdk--").removeprefix("otdfctl--")

    sdk_dirs = get_sdk_dirs()
    for sdk in sdks:
        print(f"Checking out and building {sdk} from source ({expanded})...")
        make_dir = sdk_dirs[sdk]
        env = os.environ.copy()
        env["VERSIONS"] = slug
        if sdk == "go":
            platform_dir = checkout_go_from_platform(expanded)
            env["GOWORK"] = str(platform_dir / "go.work")
        else:
            checkout_sdk_branch(sdk, expanded)
        subprocess.check_call(["make"], cwd=make_dir, env=env)
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
