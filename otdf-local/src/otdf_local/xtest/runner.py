"""xtest runner - installs SDKs, manages services, runs test phases."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from otdf_local.config.settings import Settings
from otdf_local.utils.console import (
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from otdf_local.xtest.config import ResolvedVersion, TestPhase, XtestConfig
from otdf_local.xtest.resolve import _find_sdk_mgr_dir, detect_features


def install_sdks(config: XtestConfig, settings: Settings) -> bool:
    """Install SDK CLIs based on resolved version info.

    For released versions, calls `otdf-sdk-mgr install artifact`.
    For head versions, calls `otdf-sdk-mgr checkout` then `make`.

    Returns True if all installs succeeded.
    """
    sdk_mgr_dir = _find_sdk_mgr_dir(settings)
    sdk_base = settings.xtest_root / "sdk"
    ok = True

    for sdk_type in ("go", "js", "java"):
        versions = config.resolved.get(sdk_type, [])
        for v in versions:
            if v.err:
                print_warning(f"Skipping {sdk_type} {v.tag}: has errors")
                continue

            if v.head:
                ok = _install_from_source(sdk_type, v, sdk_mgr_dir, sdk_base) and ok
            elif v.release:
                ok = _install_artifact(sdk_type, v, sdk_mgr_dir, sdk_base) and ok
            else:
                print_warning(f"Skipping {sdk_type} {v.tag}: neither head nor release")

    return ok


def _install_artifact(
    sdk_type: str,
    version: ResolvedVersion,
    sdk_mgr_dir: Path,
    sdk_base: Path,
) -> bool:
    """Install a released SDK artifact via otdf-sdk-mgr."""
    print_info(f"Installing {sdk_type} {version.tag} from artifact...")
    cmd = [
        "uv",
        "run",
        "--project",
        str(sdk_mgr_dir),
        "otdf-sdk-mgr",
        "install",
        "artifact",
        "--sdk",
        sdk_type,
        "--version",
        version.tag,
    ]
    if version.source:
        cmd.extend(["--source", version.source])

    result = subprocess.run(cmd, cwd=str(sdk_base / sdk_type))
    if result.returncode != 0:
        print_error(
            f"Failed to install {sdk_type} {version.tag} artifact, trying source..."
        )
        return _install_from_source(sdk_type, version, sdk_mgr_dir, sdk_base)

    print_success(f"Installed {sdk_type} {version.tag}")
    return True


def _install_from_source(
    sdk_type: str,
    version: ResolvedVersion,
    sdk_mgr_dir: Path,
    sdk_base: Path,
) -> bool:
    """Checkout and build an SDK from source."""
    print_info(f"Building {sdk_type} {version.tag} from source...")

    # Checkout
    cmd = [
        "uv",
        "run",
        "--project",
        str(sdk_mgr_dir),
        "otdf-sdk-mgr",
        "checkout",
        sdk_type,
        version.tag,
    ]
    result = subprocess.run(cmd, cwd=str(sdk_base / sdk_type))
    if result.returncode != 0:
        print_error(f"Failed to checkout {sdk_type} {version.tag}")
        return False

    # Build
    result = subprocess.run(["make"], cwd=str(sdk_base / sdk_type))
    if result.returncode != 0:
        print_error(f"Failed to build {sdk_type} {version.tag}")
        return False

    print_success(f"Built {sdk_type} {version.tag} from source")
    return True


def run_phase(
    phase: TestPhase,
    config: XtestConfig,
    settings: Settings,
) -> bool:
    """Run a single test phase.

    Returns True if pytest exited successfully.
    """
    xtest_dir = settings.xtest_root

    # Build pytest command
    cmd = ["uv", "run", "pytest"]
    cmd.extend(phase.pytest_args)
    cmd.extend(["-ra", "-v"])

    # Add focus/encrypt SDK flags
    cmd.extend(["--sdks-encrypt", config.encrypt_sdk])
    if config.inputs.focus_sdk != "all":
        cmd.extend(["--focus", config.inputs.focus_sdk])

    # Add HTML report
    report_name = f"{phase.name}-{config.encrypt_sdk}-{config.platform_tag}"
    cmd.extend(
        [
            "--html",
            f"test-results/{report_name}.html",
            "--self-contained-html",
        ]
    )

    # Add test files
    cmd.extend(phase.test_files)

    # Build environment
    env = _build_phase_env(config, settings, phase)

    print_info(f"Running phase: {phase.name}")
    print_info(f"  Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=str(xtest_dir), env=env)

    if result.returncode == 0:
        print_success(f"Phase {phase.name} passed")
        return True
    else:
        print_error(f"Phase {phase.name} failed (exit code {result.returncode})")
        return False


def _build_phase_env(
    config: XtestConfig,
    settings: Settings,
    phase: TestPhase,
) -> dict[str, str]:
    """Build environment variables for a test phase."""
    env = dict(os.environ)

    # Core variables
    env["PLATFORM_TAG"] = config.platform_tag
    env["PLATFORM_DIR"] = str(settings.platform_dir.resolve())
    env["PLATFORMURL"] = settings.platform_url
    env["ENCRYPT_SDK"] = config.encrypt_sdk
    env["FOCUS_SDK"] = config.inputs.focus_sdk

    # Schema file
    schema_file = settings.platform_dir / "sdk" / "schema" / "manifest.schema.json"
    if schema_file.exists():
        env["SCHEMA_FILE"] = str(schema_file.resolve())
    else:
        # Fallback to xtest-local manifest.schema.json
        local_schema = settings.xtest_root / "manifest.schema.json"
        if local_schema.exists():
            env["SCHEMA_FILE"] = "manifest.schema.json"

    # Log files
    platform_log = settings.logs_dir / "platform.log"
    if platform_log.exists():
        env["PLATFORM_LOG_FILE"] = str(platform_log.resolve())

    kas_env_mapping = {
        "alpha": "KAS_ALPHA_LOG_FILE",
        "beta": "KAS_BETA_LOG_FILE",
        "gamma": "KAS_GAMMA_LOG_FILE",
        "delta": "KAS_DELTA_LOG_FILE",
        "km1": "KAS_KM1_LOG_FILE",
        "km2": "KAS_KM2_LOG_FILE",
    }
    for kas_name, env_var in kas_env_mapping.items():
        log_path = settings.get_kas_log_path(kas_name)
        if log_path.exists():
            env[env_var] = str(log_path.resolve())

    # Root key
    from otdf_local.utils.yaml import get_nested, load_yaml

    try:
        platform_config = load_yaml(settings.platform_config)
        root_key = get_nested(platform_config, "services.kas.root_key")
        if root_key:
            env["OT_ROOT_KEY"] = root_key
    except Exception:
        pass

    # Phase-specific env overrides
    env.update(phase.env)

    return env


def run_xtest(
    config: XtestConfig,
    settings: Settings,
    phase_name: str | None = None,
    skip_services: bool = False,
    skip_install: bool = False,
) -> bool:
    """Execute the full xtest lifecycle.

    Args:
        config: Parsed xtest configuration
        settings: otdf-local settings
        phase_name: Run only this phase (None = all phases)
        skip_services: Don't start/stop services
        skip_install: Don't install SDKs

    Returns:
        True if all phases passed
    """
    # Ensure test-results directory exists
    results_dir = settings.xtest_root / "test-results"
    results_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Install SDKs
    if not skip_install:
        print_info("Installing SDK CLIs...")
        if not install_sdks(config, settings):
            print_warning("Some SDK installs failed; continuing with available SDKs")

    # Step 2: Start services
    if not skip_services:
        print_info("Starting services...")
        from otdf_local.cli import up

        try:
            up(services=None, no_provision=False)
        except SystemExit as e:
            if e.code != 0:
                print_error("Failed to start services")
                return False

    # Step 3: Re-detect features from running platform
    try:
        config.features = detect_features(settings)
        print_info(
            f"Features: ec-tdf={config.features.ec_tdf}, "
            f"key-management={config.features.key_management}, "
            f"multikas={config.features.multikas}"
        )
    except Exception as e:
        print_warning(f"Could not detect features: {e}")

    # Step 4: Run phases
    phases = config.phases
    if phase_name:
        phases = [p for p in phases if p.name == phase_name]
        if not phases:
            valid = ", ".join(p.name for p in config.phases)
            print_error(f"Unknown phase: {phase_name}. Valid phases: {valid}")
            return False

    all_passed = True
    results: list[tuple[str, bool, str]] = []

    for phase in phases:
        # Check requirements
        if not config.check_phase_requirements(phase):
            reason = f"unmet requirements: {', '.join(phase.requires)}"
            print_warning(f"Skipping phase {phase.name}: {reason}")
            results.append((phase.name, True, "skipped"))
            continue

        passed = run_phase(phase, config, settings)
        results.append((phase.name, passed, "passed" if passed else "FAILED"))
        if not passed:
            all_passed = False

    # Print summary
    console.print()
    console.print("[bold]Test Summary[/bold]")
    for name, passed, status in results:
        icon = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        if status == "skipped":
            icon = "[yellow]SKIP[/yellow]"
        console.print(f"  {icon} {name}")

    return all_passed
