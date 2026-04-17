"""Runner for X-Test suites."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from otdf_local.config.settings import Settings
from otdf_local.services import (
    Provisioner,
    get_docker_service,
    get_kas_manager,
    get_platform_service,
    get_provisioner,
)
from otdf_local.suite.models import PlatformVersion, SDKVersion, SuiteConfig, TestJob
from otdf_local.utils.console import (
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
    status_spinner,
)


class SuiteRunner:
    """Orchestrates the execution of an X-Test suite."""

    def __init__(self, config: SuiteConfig, settings: Settings) -> None:
        self.config = config
        self.settings = settings
        self.results: List[Dict] = []

    def run(self) -> bool:
        """Run the full suite."""
        success = True

        for platform in self.config.platforms:
            if not self._run_platform_tests(platform):
                success = False

        self._print_summary()
        return success

    def _run_platform_tests(self, platform: PlatformVersion) -> bool:
        """Run all tests against a specific platform version."""
        print_info(f"--- Starting tests for Platform {platform.tag} ---")

        # 1. Checkout platform if needed
        platform_dir = self._ensure_platform(platform)
        if not platform_dir:
            return False

        # Create a specific settings instance for this platform
        # We need to be careful with global state in otdf-local
        # but for now we'll just update the settings object.
        original_platform_dir = self.settings.platform_dir
        self.settings.platform_dir = platform_dir

        try:
            # 2. Start Services
            if not self._start_services(platform):
                return False

            # 3. Install SDKs
            self._ensure_sdks()

            # 4. Run Jobs
            platform_success = True
            for job in self.config.jobs:
                if not self._run_job(job, platform):
                    platform_success = False

            return platform_success

        finally:
            self._stop_services()
            self.settings.platform_dir = original_platform_dir

    def _ensure_platform(self, platform: PlatformVersion) -> Optional[Path]:
        """Ensure the platform is checked out at the right version."""
        # Use otdf-sdk-mgr to checkout platform
        ref = platform.sha or platform.tag
        print_info(f"Ensuring platform version {ref}...")
        sdk_mgr_dir = self.settings.xtest_root / "otdf-sdk-mgr"
        try:
            subprocess.check_call(
                ["uv", "run", "--project", str(sdk_mgr_dir), "otdf-sdk-mgr", "checkout", "platform", ref],
                cwd=sdk_mgr_dir,
            )
            # Find the worktree path. otdf-sdk-mgr puts it in xtest/sdk/platform/src/<branch>
            # where branch has / replaced with --
            branch_dir = ref.replace("/", "--")
            if branch_dir.startswith("service--"):
                branch_dir = branch_dir.removeprefix("service--")

            worktree_path = (
                self.settings.xtest_root / "sdk" / "platform" / "src" / branch_dir
            )
            if not worktree_path.exists():
                 # Fallback to direct directory if tag is 'main' and we are already in platform dir?
                 # No, better be explicit. otdf-sdk-mgr puts main in 'main'
                 pass

            if not worktree_path.exists():
                print_error(f"Platform worktree not found at {worktree_path}")
                return None

            return worktree_path
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to checkout platform {platform.tag}: {e}")
            return None

    def _ensure_sdks(self) -> None:
        """Ensure all required SDKs are installed."""
        sdk_mgr_dir = self.settings.xtest_root / "otdf-sdk-mgr"
        for sdk, versions in self.config.sdks.items():
            for version in versions:
                ref = version.sha or version.tag
                print_info(f"Ensuring {sdk} {ref}...")
                
                # If it's a SHA or a tag we want to build from source, we use 'checkout'
                if version.sha or version.head:
                    args = ["uv", "run", "--project", str(sdk_mgr_dir), "otdf-sdk-mgr", "checkout", sdk, ref]
                    try:
                        subprocess.check_call(
                            args,
                            cwd=sdk_mgr_dir,
                        )
                        # After checkout, we need to build it
                        sdk_dir = self.settings.xtest_root / "sdk" / sdk
                        print_info(f"Building {sdk} from source in {sdk_dir}...")
                        subprocess.check_call(["make"], cwd=sdk_dir)
                    except subprocess.CalledProcessError as e:
                        print_warning(f"Failed to checkout/build {sdk} {ref}: {e}")
                else:
                    args = ["uv", "run", "--project", str(sdk_mgr_dir), "otdf-sdk-mgr", "install", "artifact", "--sdk", sdk, "--version", ref]
                    if version.source:
                        args.extend(["--source", version.source])
                    if version.alias:
                        args.extend(["--dist-name", version.alias])

                    try:
                        subprocess.check_call(
                            args,
                            cwd=sdk_mgr_dir,
                        )
                    except subprocess.CalledProcessError as e:
                        print_warning(f"Failed to install {sdk} {ref}: {e}")

    def _start_services(self, platform: PlatformVersion) -> bool:
        """Start Docker, Platform, and optionally KAS."""
        print_info("Starting services...")

        # Update platform config if extra_keys provided
        if platform.extra_keys:
            # We'll handle this by writing to extra-keys.json if it's a JSON string
            # or just assume xtest/extra-keys.json is used by PlatformService._setup_golden_keys
            pass

        # Start Docker
        docker = get_docker_service(self.settings)
        if not docker.start():
            return False

        # Start Platform
        platform_service = get_platform_service(self.settings)
        if not platform_service.start():
            return False

        with status_spinner("Waiting for Platform..."):
            from otdf_local.health.waits import wait_for_health
            try:
                wait_for_health(platform_service.health_url, timeout=120)
            except Exception as e:
                print_error(f"Platform failed to become healthy: {e}")
                return False

        # Provision
        provisioner = get_provisioner(self.settings)
        provisioner.provision_all()

        return True

    def _run_job(self, job: TestJob, platform: PlatformVersion) -> bool:
        """Run a specific test job."""
        print_info(f"Running job: {job.name}")

        # Start KAS if needed
        if job.requires_kas:
            print_info("Starting KAS instances for ABAC tests...")
            kas_manager = get_kas_manager(self.settings)
            kas_manager.start_all()
            # Wait for health...
            # (simplified for now, PlatformService.start already waits for platform)

        # Build pytest command
        cmd = ["uv", "run", "pytest"] + job.pytest_args

        # Environment variables
        env = os.environ.copy()
        # Add otdf-local env vars
        from otdf_local.cli import env as env_cmd
        # We can't easily call 'env' command here without stdout capture
        # Let's just manually set the essentials
        env["PLATFORMURL"] = self.settings.platform_url
        env["PLATFORM_DIR"] = str(self.settings.platform_dir.resolve())
        env["OT_ROOT_KEY"] = self._get_root_key()
        env["FOCUS_SDK"] = job.focus_sdk

        # Run pytest
        print_info(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            cwd=self.settings.xtest_root,
            env=env,
        )

        success = result.returncode == 0
        self.results.append({
            "job": job.name,
            "platform": platform.tag,
            "success": success,
            "returncode": result.returncode
        })

        if success:
            print_success(f"Job {job.name} passed")
        else:
            print_error(f"Job {job.name} failed with code {result.returncode}")

        return success

    def _stop_services(self) -> None:
        """Stop all services."""
        print_info("Stopping services...")
        get_kas_manager(self.settings).stop_all()
        get_platform_service(self.settings).stop()
        get_docker_service(self.settings).stop()

    def _get_root_key(self) -> str:
        """Read root key from platform config."""
        from otdf_local.utils.yaml import load_yaml, get_nested
        try:
            config = load_yaml(self.settings.platform_config)
            return get_nested(config, "services.kas.root_key") or ""
        except:
            return ""

    def _print_summary(self) -> None:
        """Print a summary of all test results."""
        console.print("\n[bold]--- Test Suite Summary ---[/bold]")
        all_passed = True
        for res in self.results:
            status = "[green]PASS[/green]" if res["success"] else "[red]FAIL[/red]"
            console.print(f"{status} Job: {res['job']} (Platform: {res['platform']})")
            if not res["success"]:
                all_passed = False

        if all_passed:
            print_success("All tests passed!")
        else:
            print_error("Some tests failed.")
