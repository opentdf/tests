"""Typer CLI for otdf_local - OpenTDF test environment management."""

import json
import shutil
import subprocess
import sys
import time
from typing import Annotated

import httpx
import typer
from rich.live import Live

from otdf_local import __version__
from otdf_local.config.ports import Ports
from otdf_local.config.settings import get_settings
from otdf_local.health.waits import WaitTimeoutError, wait_for_health, wait_for_port
from otdf_local.process.logs import LogAggregator, LogEntry
from otdf_local.services import (
    Provisioner,
    ProvisionResult,
    get_docker_service,
    get_kas_manager,
    get_platform_service,
    get_provisioner,
)
from otdf_local.utils.console import (
    console,
    create_service_table,
    format_health,
    format_status,
    print_error,
    print_info,
    print_success,
    print_warning,
    status_spinner,
)
from otdf_local.utils.yaml import get_nested, load_yaml

app = typer.Typer(
    name="otdf-local",
    help="Local management CLI for OpenTDF test environment",
    no_args_is_help=True,
    pretty_exceptions_enable=sys.stderr.isatty(),
)


def _show_provision_error(result: ProvisionResult, target: str) -> None:
    """Display provisioning error with stderr details."""
    print_error(f"{target} provisioning failed (exit code {result.return_code})")

    if result.stderr:
        # Show last 15 lines of stderr
        lines = result.stderr.strip().split("\n")[-15:]
        console.print("\n[dim]Error output:[/dim]")
        for line in lines:
            console.print(f"  {line}")


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"otdf-local version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """OpenTDF test environment management CLI."""
    pass


@app.command()
def up(
    services: Annotated[
        str | None,
        typer.Option(
            "--services",
            "-s",
            help="Comma-separated list of services to start (docker,platform,kas)",
        ),
    ] = None,
    no_provision: Annotated[
        bool,
        typer.Option("--no-provision", help="Skip provisioning step"),
    ] = False,
) -> None:
    """Start the test environment.

    By default starts all services: docker (keycloak, postgres), platform, and all KAS instances.
    """
    settings = get_settings()
    settings.ensure_directories()

    # Parse services to start
    if services:
        service_list = [s.strip().lower() for s in services.split(",")]
    else:
        service_list = ["docker", "platform", "kas"]

    start_docker = "docker" in service_list
    start_platform = "platform" in service_list
    start_kas = "kas" in service_list

    # Step 1: Start Docker services
    if start_docker:
        print_info("Starting Docker services (Keycloak, PostgreSQL)...")
        docker = get_docker_service(settings)
        if not docker.start():
            print_error("Failed to start Docker services")
            raise typer.Exit(1)

        with status_spinner("Waiting for Keycloak..."):
            try:
                wait_for_health(
                    f"http://localhost:{Ports.KEYCLOAK}/auth/realms/master",
                    timeout=120,
                    service_name="Keycloak",
                )
            except WaitTimeoutError as e:
                print_error(str(e))
                raise typer.Exit(1) from e
        print_success("Keycloak is ready")

        print_info("Waiting for PostgreSQL...")
        try:
            wait_for_port(
                Ports.POSTGRES,
                "localhost",
                timeout=60,
                service_name="PostgreSQL",
            )
        except WaitTimeoutError as e:
            print_error(str(e))
            raise typer.Exit(1) from e
        print_success("PostgreSQL is ready")

        if not no_provision:
            print_info("Provisioning Keycloak...")
            provisioner: Provisioner = get_provisioner(settings)
            result = provisioner.provision_keycloak()
            if not result:
                _show_provision_error(result, "Keycloak")
                raise typer.Exit(1)
            print_success("Keycloak provisioned")

    # Step 2: Start Platform
    if start_platform:
        print_info("Starting Platform...")
        platform = get_platform_service(settings)
        if not platform.start():
            print_error("Failed to start Platform")
            raise typer.Exit(1)

        with status_spinner("Waiting for Platform..."):
            try:
                wait_for_health(
                    f"http://localhost:{Ports.PLATFORM}/healthz",
                    timeout=120,
                    service_name="Platform",
                )
            except WaitTimeoutError as e:
                print_error(str(e))
                raise typer.Exit(1) from e
        print_success("Platform is ready")

    # Step 3: Provision
    if start_platform and not no_provision:
        print_info("Provisioning fixtures...")
        provisioner = get_provisioner(settings)
        result = provisioner.provision_fixtures()
        if not result:
            _show_provision_error(result, "Fixtures")
            print_warning("Provisioning had issues - continuing anyway")
        else:
            print_success("Provisioning complete")

    # Step 4: Start KAS instances
    if start_kas:
        print_info("Starting KAS instances...")
        kas_manager = get_kas_manager(settings)
        results = kas_manager.start_all()

        failed = [name for name, ok in results.items() if not ok]
        if failed:
            print_error(f"Failed to start KAS instances: {', '.join(failed)}")
            raise typer.Exit(1)

        with status_spinner("Waiting for KAS instances..."):
            for kas_name in Ports.all_kas_names():
                port = Ports.get_kas_port(kas_name)
                try:
                    wait_for_health(
                        f"http://localhost:{port}/healthz",
                        timeout=60,
                        service_name=f"KAS {kas_name}",
                    )
                except WaitTimeoutError as e:
                    print_warning(str(e))
        print_success("KAS instances are ready")

    print_success("Environment is up!")


@app.command()
def down(
    clean: Annotated[
        bool,
        typer.Option("--clean", help="Also clean logs and generated configs"),
    ] = False,
) -> None:
    """Stop all services."""
    settings = get_settings()

    # Stop KAS instances
    print_info("Stopping KAS instances...")
    kas_manager = get_kas_manager(settings)
    kas_manager.stop_all()

    # Stop Platform
    print_info("Stopping Platform...")
    platform = get_platform_service(settings)
    platform.stop()

    # Stop Docker
    print_info("Stopping Docker services...")
    docker = get_docker_service(settings)
    docker.stop()

    if clean:
        print_info("Cleaning up...")
        _do_clean(settings, keep_logs=False)

    print_success("Environment stopped")


@app.command(name="ls")
def list_services(
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
    all_services: Annotated[
        bool,
        typer.Option("--all", "-a", help="Include stopped services"),
    ] = False,
) -> None:
    """List all services with their status."""
    settings = get_settings()

    # Gather all service info
    docker = get_docker_service(settings)
    platform = get_platform_service(settings)
    kas_manager = get_kas_manager(settings)

    all_info = []
    all_info.extend(docker.get_all_info())
    all_info.append(platform.get_info())
    all_info.extend(kas_manager.get_all_info())

    # Filter if not showing all
    if not all_services:
        all_info = [info for info in all_info if info.running]

    if json_output:
        output = [info.to_dict() for info in all_info]
        console.print_json(json.dumps(output))
        return

    # Table output
    table = create_service_table()
    for info in all_info:
        table.add_row(
            info.name,
            str(info.port),
            info.service_type.value,
            format_status(info.running),
            format_health(info.healthy),
        )

    console.print(table)


@app.command()
def status(
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
    watch: Annotated[
        bool,
        typer.Option("--watch", "-w", help="Continuously update status"),
    ] = False,
) -> None:
    """Show detailed status with health checks."""
    settings = get_settings()

    def get_status_table():
        docker = get_docker_service(settings)
        platform = get_platform_service(settings)
        kas_manager = get_kas_manager(settings)

        all_info = []
        all_info.extend(docker.get_all_info())
        all_info.append(platform.get_info())
        all_info.extend(kas_manager.get_all_info())

        if json_output:
            return json.dumps([info.to_dict() for info in all_info], indent=2)

        table = create_service_table()
        for info in all_info:
            table.add_row(
                info.name,
                str(info.port),
                info.service_type.value,
                format_status(info.running),
                format_health(info.healthy),
            )
        return table

    if watch:
        with Live(get_status_table(), refresh_per_second=1, console=console) as live:
            while True:
                time.sleep(1)
                live.update(get_status_table())
    else:
        result = get_status_table()
        if json_output:
            console.print(result)
        else:
            console.print(result)


@app.command()
def logs(
    service: Annotated[
        str | None,
        typer.Argument(help="Service name (platform, kas-alpha, etc.)"),
    ] = None,
    follow: Annotated[
        bool,
        typer.Option("--follow", "-f", help="Follow log output"),
    ] = False,
    lines: Annotated[
        int,
        typer.Option("--lines", "-n", help="Number of lines to show"),
    ] = 50,
    grep: Annotated[
        str | None,
        typer.Option("--grep", "-g", help="Filter by regex pattern"),
    ] = None,
) -> None:
    """View service logs.

    Without a service name, shows aggregated logs from all services.
    """
    settings = get_settings()
    aggregator = LogAggregator(settings.logs_dir)

    # Add all services to aggregator
    aggregator.add_service("platform")
    for kas_name in Ports.all_kas_names():
        aggregator.add_service(f"kas-{kas_name}")

    # Determine which services to show
    services_filter = [service] if service else None

    if follow:
        print_info("Following logs (Ctrl+C to stop)...")
        try:
            for entry in aggregator.follow(services=services_filter):
                if grep and grep.lower() not in entry.message.lower():
                    continue
                _print_log_entry(entry)
        except KeyboardInterrupt:
            pass
    else:
        entries = aggregator.read_tail(n=lines, services=services_filter, pattern=grep)
        for entry in entries:
            _print_log_entry(entry)


def _print_log_entry(entry: LogEntry) -> None:
    """Format and print a log entry."""
    timestamp = ""
    if entry.timestamp:
        timestamp = entry.timestamp.strftime("%H:%M:%S")
    console.print(
        f"[dim]{timestamp}[/dim] [cyan]{entry.service}[/cyan] {entry.message}"
    )


@app.command()
def clean(
    keep_logs: Annotated[
        bool,
        typer.Option("--keep-logs", help="Keep log files"),
    ] = False,
) -> None:
    """Clean up generated files and logs."""
    settings = get_settings()
    _do_clean(settings, keep_logs)
    print_success("Cleanup complete")


def _do_clean(settings, keep_logs: bool) -> None:
    """Perform cleanup."""
    # Clean config directory
    if settings.config_dir.exists():
        shutil.rmtree(settings.config_dir)
        settings.config_dir.mkdir(parents=True, exist_ok=True)

    # Clean logs unless keeping them
    if not keep_logs and settings.logs_dir.exists():
        shutil.rmtree(settings.logs_dir)
        settings.logs_dir.mkdir(parents=True, exist_ok=True)


@app.command()
def provision(
    target: Annotated[
        str,
        typer.Argument(help="What to provision: keycloak, fixtures, or all"),
    ] = "all",
) -> None:
    """Run provisioning steps."""
    settings = get_settings()
    provisioner = get_provisioner(settings)

    if target == "all":
        print_info("Running all provisioning...")
        result = provisioner.provision_all()
        if result:
            print_success("Provisioning complete")
        else:
            _show_provision_error(result, "Provisioning")
            raise typer.Exit(1)
    elif target == "keycloak":
        print_info("Provisioning Keycloak...")
        result = provisioner.provision_keycloak()
        if result:
            print_success("Keycloak provisioning complete")
        else:
            _show_provision_error(result, "Keycloak")
            raise typer.Exit(1)
    elif target == "fixtures":
        print_info("Provisioning fixtures...")
        result = provisioner.provision_fixtures()
        if result:
            print_success("Fixtures provisioning complete")
        else:
            _show_provision_error(result, "Fixtures")
            raise typer.Exit(1)
    else:
        print_error(f"Unknown target: {target}")
        print_info("Valid targets: keycloak, fixtures, all")
        raise typer.Exit(1)


@app.command()
def restart(
    service: Annotated[
        str,
        typer.Argument(help="Service to restart (platform, kas-alpha, docker, etc.)"),
    ],
) -> None:
    """Restart a specific service."""
    settings = get_settings()

    if service == "docker":
        print_info("Restarting Docker services...")
        docker = get_docker_service(settings)
        docker.stop()
        docker.start()
        print_success("Docker services restarted")
        return

    if service == "platform":
        print_info("Restarting Platform...")
        platform = get_platform_service(settings)
        platform.restart()
        print_success("Platform restarted")
        return

    if service.startswith("kas-"):
        kas_name = service[4:]  # Remove "kas-" prefix
        if kas_name not in Ports.all_kas_names():
            print_error(f"Unknown KAS instance: {kas_name}")
            print_info(f"Valid KAS names: {', '.join(Ports.all_kas_names())}")
            raise typer.Exit(1)

        print_info(f"Restarting KAS {kas_name}...")
        kas_manager = get_kas_manager(settings)
        kas = kas_manager.get(kas_name)
        if kas:
            kas.restart()
            print_success(f"KAS {kas_name} restarted")
        else:
            print_error(f"KAS {kas_name} not found")
            raise typer.Exit(1)
        return

    # Check for KAS name without prefix
    if service in Ports.all_kas_names():
        print_info(f"Restarting KAS {service}...")
        kas_manager = get_kas_manager(settings)
        kas = kas_manager.get(service)
        if kas:
            kas.restart()
            print_success(f"KAS {service} restarted")
        return

    print_error(f"Unknown service: {service}")
    print_info(
        "Valid services: docker, platform, kas-alpha, kas-beta, kas-gamma, kas-delta, kas-km1, kas-km2"
    )
    raise typer.Exit(1)


@app.command()
def env(
    format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format: shell (default), json",
        ),
    ] = "shell",
) -> None:
    """Output environment variables for pytest.

    Use this command to configure your shell environment for running tests:

        eval $(otdf-local env)

    Or source it directly:

        . <(otdf-local env)

    This sets variables like PLATFORM_LOG_FILE, KAS_*_LOG_FILE, PLATFORMURL, OT_ROOT_KEY, etc.
    """
    settings = get_settings()

    # Build environment variable dict
    env_vars = {}

    # Platform configuration
    env_vars["PLATFORMURL"] = settings.platform_url
    env_vars["PLATFORM_DIR"] = str(settings.platform_dir.resolve())

    # Schema file for manifest validation
    schema_file = settings.platform_dir / "sdk" / "schema" / "manifest.schema.json"
    if schema_file.exists():
        env_vars["SCHEMA_FILE"] = str(schema_file.resolve())

    # Log file paths
    platform_log = settings.logs_dir / "platform.log"
    if platform_log.exists():
        env_vars["PLATFORM_LOG_FILE"] = str(platform_log.resolve())

    # KAS log files
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
            env_vars[env_var] = str(log_path.resolve())

    # Read platform config to get root key
    try:
        platform_config = load_yaml(settings.platform_config)
        root_key = get_nested(platform_config, "services.kas.root_key")
        if root_key:
            env_vars["OT_ROOT_KEY"] = root_key
    except Exception as e:
        print_warning(f"Could not read root key from platform config: {e}")

    # Try to get platform version from API
    try:
        platform = get_platform_service(settings)
        if platform.is_running():
            resp = httpx.get(
                f"{settings.platform_url}/.well-known/opentdf-configuration",
                timeout=5,
            )
            if resp.status_code == 200:
                config = resp.json()
                if "version" in config:
                    env_vars["PLATFORM_VERSION"] = config["version"]
    except Exception as e:
        print_warning(f"Could not get platform version from API: {e}")

    # Fall back to git describe if API didn't provide version
    if "PLATFORM_VERSION" not in env_vars:
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--match", "service/v*"],
                capture_output=True,
                text=True,
                cwd=settings.platform_dir,
                timeout=5,
            )
            if result.returncode == 0:
                # Parse "service/v0.13.0" or "service/v0.13.0-1-gabcdef"
                tag = result.stdout.strip()
                if tag.startswith("service/v"):
                    version = tag[len("service/v") :]
                    # Strip git describe suffix (e.g. "-1-gabcdef")
                    parts = version.split("-")
                    if len(parts) >= 3 and parts[-1].startswith("g"):
                        version = "-".join(parts[:-2])
                    env_vars["PLATFORM_VERSION"] = version
        except Exception as e:
            print_warning(f"Could not get platform version from git: {e}")

    # Output in requested format
    if format == "json":
        console.print_json(json.dumps(env_vars, indent=2))
    else:
        # Shell export format - use plain print to avoid line wrapping
        for key, value in env_vars.items():
            # Escape single quotes in value for shell safety
            escaped_value = value.replace("'", "'\\''")
            # Use plain print to stdout to avoid rich console line wrapping
            print(f"export {key}='{escaped_value}'", file=sys.stdout)


if __name__ == "__main__":
    app()
