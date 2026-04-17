"""CLI commands for X-Test suite management."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Optional

import typer
import yaml

from otdf_local.config.settings import get_settings
from otdf_local.suite.models import (
    PlatformVersion,
    SDKVersion,
    SuiteConfig,
    TestJob,
)
from otdf_local.utils.console import console, print_error, print_info


suite_app = typer.Typer(
    name="suite",
    help="X-Test suite orchestration commands.",
    no_args_is_help=True,
)


@suite_app.command("generate-shard")
def generate_shard(
    platform_ref: Annotated[str, typer.Option("--platform-ref", help="Platform ref to test")] = ...,
    sdk: Annotated[str, typer.Option("--sdk", help="SDK to focus on (go, java, js)")] = ...,
    platform_sha: Annotated[Optional[str], typer.Option("--platform-sha", help="Platform SHA to test")] = None,
    go_ref: Annotated[str, typer.Option("--go-ref")] = "main",
    go_sha: Annotated[Optional[str], typer.Option("--go-sha")] = None,
    java_ref: Annotated[str, typer.Option("--java-ref")] = "main",
    java_sha: Annotated[Optional[str], typer.Option("--java-sha")] = None,
    js_ref: Annotated[str, typer.Option("--js-ref")] = "main",
    js_sha: Annotated[Optional[str], typer.Option("--js-sha")] = None,
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Output YAML file")] = None,
) -> None:
    """Generate a self-contained SuiteConfig YAML for a specific matrix shard."""
    platform = PlatformVersion(tag=platform_ref, sha=platform_sha)
    
    sdks = {
        "go": [SDKVersion(tag=go_ref, sha=go_sha)],
        "java": [SDKVersion(tag=java_ref, sha=java_sha)],
        "js": [SDKVersion(tag=js_ref, sha=js_sha)],
    }
    
    # Define jobs - match the standard jobs in xtest.yml
    jobs = [
        TestJob(
            name=f"standard-{sdk}",
            pytest_args=["-ra", "-v", "test_tdfs.py", "test_policytypes.py"],
            focus_sdk=sdk
        ),
        TestJob(
            name=f"legacy-{sdk}",
            pytest_args=["-ra", "-v", "test_legacy.py"],
            focus_sdk=sdk
        ),
        TestJob(
            name=f"abac-{sdk}",
            pytest_args=["-ra", "-v", "test_abac.py"],
            focus_sdk=sdk,
            requires_kas=True
        ),
    ]
    
    config = SuiteConfig(
        platforms=[platform],
        sdks=sdks,
        jobs=jobs
    )
    
    yaml_data = yaml.dump(config.model_dump(), sort_keys=False)
    
    if output:
        output.write_text(yaml_data)
        print_info(f"Generated shard config at {output}")
    else:
        # Print to stdout (wrapped in markdown for GHA summary)
        summary = f"<details><summary><b>shard.yaml</b> (for reproduction)</summary>\n\n```yaml\n{yaml_data}```\n</details>"
        console.print(summary)
        
        # Also write to GITHUB_STEP_SUMMARY if it exists
        github_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if github_summary:
            with open(github_summary, "a") as f:
                f.write(f"\n{summary}\n")


@suite_app.command("run")
def run_suite(
    config_path: Annotated[Path, typer.Argument(help="Path to SuiteConfig YAML")],
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose logging")] = False,
) -> None:
    """Run an X-Test suite from a configuration file."""
    if not config_path.exists():
        print_error(f"Config file not found: {config_path}")
        raise typer.Exit(1)
    
    with open(config_path) as f:
        data = yaml.safe_load(f)
        config = SuiteConfig.model_validate(data)
    
    from otdf_local.suite.runner import SuiteRunner
    runner = SuiteRunner(config, get_settings(), verbose=verbose)
    
    success = runner.run()
    if not success:
        raise typer.Exit(1)
