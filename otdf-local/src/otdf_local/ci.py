"""CI-specific commands for otdf-local.

These commands adapt the local environment management for GitHub Actions CI,
where the platform is already started by an external action and we only need
to start KAS instances as background processes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from otdf_local.config.ports import Ports
from otdf_local.config.settings import Settings
from otdf_local.health.waits import WaitTimeoutError, wait_for_health
from otdf_local.services import get_kas_manager
from otdf_local.utils.console import (
    print_error,
    print_info,
    print_success,
    print_warning,
)
from otdf_local.utils.yaml import load_yaml, save_yaml, set_nested

ci_app = typer.Typer(
    name="ci",
    help="CI-specific commands for GitHub Actions workflows.",
    no_args_is_help=True,
)


def _emit_github_output(key: str, value: str) -> None:
    """Write a key=value pair to $GITHUB_OUTPUT if available, else print to stdout."""
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"{key}={value}\n")
    else:
        # Fallback for local testing
        print(f"{key}={value}", file=sys.stdout)


def _prepare_kas_template(
    settings: Settings, root_key: str | None, ec_tdf_enabled: bool
) -> None:
    """Ensure the KAS template config has the right root key and EC TDF settings.

    In CI, the platform config may have a root_key that differs from what
    we want for additional KAS instances. This updates the platform config
    in-place so that KASService._generate_config reads the correct root_key.
    """
    if root_key:
        config = load_yaml(settings.platform_config)
        set_nested(config, "services.kas.root_key", root_key)
        if ec_tdf_enabled:
            set_nested(config, "services.kas.preview.ec_tdf_enabled", True)
        save_yaml(settings.platform_config, config)


@ci_app.command("start-kas")
def start_kas(
    platform_dir: Annotated[
        Path,
        typer.Option(
            "--platform-dir",
            help="Path to the platform checkout (must contain opentdf-kas-mode.yaml)",
            envvar="OTDF_LOCAL_PLATFORM_DIR",
        ),
    ],
    root_key: Annotated[
        str | None,
        typer.Option(
            "--root-key",
            help="Root key for KAS instances (overrides platform config value)",
            envvar="OT_ROOT_KEY",
        ),
    ] = None,
    ec_tdf_enabled: Annotated[
        bool,
        typer.Option(
            "--ec-tdf-enabled/--no-ec-tdf",
            help="Enable EC TDF support",
        ),
    ] = True,
    key_management: Annotated[
        bool,
        typer.Option(
            "--key-management/--no-key-management",
            help="Enable key management on km1/km2 instances",
        ),
    ] = False,
    log_type: Annotated[
        str,
        typer.Option(
            "--log-type",
            help="Log format type (json, text)",
        ),
    ] = "json",
    health_timeout: Annotated[
        int,
        typer.Option(
            "--health-timeout",
            help="Seconds to wait for each KAS instance to become healthy",
        ),
    ] = 60,
    instances: Annotated[
        str | None,
        typer.Option(
            "--instances",
            help="Comma-separated KAS instance names (default: all)",
        ),
    ] = None,
) -> None:
    """Start KAS instances for CI and emit GitHub Actions outputs.

    Expects the platform to already be running (started by start-up-with-containers).
    Starts all 6 KAS instances (alpha, beta, gamma, delta, km1, km2) as background
    processes, waits for each to pass health checks, and emits log file paths as
    GitHub Actions step outputs.

    Output keys (written to $GITHUB_OUTPUT):
      kas-alpha-log-file, kas-beta-log-file, kas-gamma-log-file,
      kas-delta-log-file, kas-km1-log-file, kas-km2-log-file
    """
    platform_dir = platform_dir.resolve()
    if not platform_dir.is_dir():
        print_error(f"Platform directory does not exist: {platform_dir}")
        raise typer.Exit(1)

    # Check for required template files
    kas_template = platform_dir / "opentdf-kas-mode.yaml"
    platform_config = platform_dir / "opentdf-dev.yaml"
    if not kas_template.exists():
        # Fall back to opentdf.yaml if opentdf-kas-mode.yaml doesn't exist
        kas_template_alt = platform_dir / "opentdf.yaml"
        if kas_template_alt.exists():
            print_info(
                f"Using {kas_template_alt} as KAS template (opentdf-kas-mode.yaml not found)"
            )
        else:
            print_error(
                f"Neither opentdf-kas-mode.yaml nor opentdf.yaml found in {platform_dir}"
            )
            raise typer.Exit(1)

    if not platform_config.exists():
        # Try opentdf.yaml as fallback
        platform_config_alt = platform_dir / "opentdf.yaml"
        if platform_config_alt.exists():
            platform_config = platform_config_alt

    # Build settings with CI-specific overrides
    # We use a fresh xtest_root derived from this package's location
    settings = Settings(
        platform_dir=platform_dir,
    )
    settings.ensure_directories()

    # Update root key in platform config if provided
    if root_key:
        _prepare_kas_template(settings, root_key, ec_tdf_enabled)

    # Determine which instances to start
    if instances:
        kas_names = [n.strip() for n in instances.split(",")]
        for name in kas_names:
            if name not in Ports.all_kas_names():
                print_error(f"Unknown KAS instance: {name}")
                raise typer.Exit(1)
    else:
        kas_names = Ports.all_kas_names()

    # Start KAS instances
    print_info(f"Starting KAS instances: {', '.join(kas_names)}...")
    kas_manager = get_kas_manager(settings)

    failed = []
    for name in kas_names:
        kas = kas_manager.get(name)
        if kas is None:
            print_error(f"KAS instance {name} not found in manager")
            failed.append(name)
            continue
        if not kas.start():
            print_error(f"Failed to start KAS {name}")
            failed.append(name)

    if failed:
        print_error(f"Failed to start: {', '.join(failed)}")
        raise typer.Exit(1)

    # Wait for health
    print_info("Waiting for KAS health checks...")
    unhealthy = []
    for name in kas_names:
        port = Ports.get_kas_port(name)
        try:
            wait_for_health(
                f"http://localhost:{port}/healthz",
                timeout=health_timeout,
                service_name=f"KAS {name}",
            )
        except WaitTimeoutError as e:
            print_warning(str(e))
            unhealthy.append(name)

    if unhealthy:
        print_error(f"KAS instances failed health check: {', '.join(unhealthy)}")
        raise typer.Exit(1)

    print_success(f"All {len(kas_names)} KAS instances are healthy")

    # Emit outputs
    for name in kas_names:
        log_path = settings.get_kas_log_path(name)
        output_key = f"kas-{name}-log-file"
        _emit_github_output(output_key, str(log_path))

    print_success("CI KAS startup complete")
