#!/usr/bin/env python3
"""Run BDD tests with the framework integration."""

import sys
import os
import subprocess
from pathlib import Path
import json
from datetime import datetime


def setup_environment():
    """Setup test environment."""
    # Set environment variables
    os.environ["TEST_ENV"] = os.getenv("TEST_ENV", "local")
    os.environ["TEST_SEED"] = os.getenv("TEST_SEED", "42")
    
    # Set service endpoints (for demo purposes)
    os.environ["KAS_URL"] = os.getenv("KAS_URL", "localhost")
    os.environ["KAS_PORT"] = os.getenv("KAS_PORT", "8080")
    os.environ["PLATFORM_URL"] = os.getenv("PLATFORM_URL", "localhost")
    os.environ["PLATFORM_PORT"] = os.getenv("PLATFORM_PORT", "8080")
    
    print("Environment setup complete")
    print(f"  TEST_ENV: {os.environ['TEST_ENV']}")
    print(f"  TEST_SEED: {os.environ['TEST_SEED']}")


def install_behave():
    """Install behave if not already installed."""
    try:
        import behave
        print(f"behave version {behave.__version__} already installed")
    except ImportError:
        print("Installing behave...")
        subprocess.run([sys.executable, "-m", "pip", "install", "behave"], check=True)
        print("behave installed successfully")


def run_bdd_tests(tags=None, profile="cross-sdk-basic", format="pretty"):
    """Run BDD tests using behave."""
    
    bdd_dir = Path(__file__).parent / "bdd"
    
    # Build behave command
    cmd = [
        sys.executable, "-m", "behave",
        str(bdd_dir),
        f"--format={format}",
        f"-D", f"profile={profile}"
    ]
    
    # Add tags filter if specified
    if tags:
        cmd.extend(["--tags", tags])
    
    # Add junit output for CI
    junit_dir = bdd_dir.parent / "test-results"
    junit_dir.mkdir(exist_ok=True)
    cmd.extend(["--junit", "--junit-directory", str(junit_dir)])
    
    print(f"\nRunning BDD tests...")
    print(f"Command: {' '.join(cmd)}")
    print("-" * 60)
    
    # Run behave
    result = subprocess.run(cmd, capture_output=False, text=True)
    
    return result.returncode


def generate_summary(artifacts_dir):
    """Generate test summary from artifacts."""
    if not artifacts_dir.exists():
        print("No artifacts found")
        return
    
    # Find latest run directory
    run_dirs = sorted([d for d in artifacts_dir.iterdir() if d.is_dir()])
    if not run_dirs:
        print("No test runs found")
        return
    
    latest_run = run_dirs[-1]
    summary_file = latest_run / "run_summary.json"
    
    if summary_file.exists():
        with open(summary_file) as f:
            summary = json.load(f)
        
        print("\n" + "=" * 60)
        print("Test Run Summary")
        print("=" * 60)
        print(f"Run ID: {summary['run_id']}")
        print(f"Total Scenarios: {summary['total_scenarios']}")
        print(f"Passed: {summary['passed']} ✓")
        print(f"Failed: {summary['failed']} ✗")
        print(f"Skipped: {summary['skipped']} ⊘")
        
        if summary['failed'] > 0:
            print("\nFailed Scenarios:")
            for evidence in summary['evidence']:
                if evidence['status'] == 'failed':
                    print(f"  - {evidence.get('scenario_name', 'Unknown')}")
                    if 'error' in evidence:
                        print(f"    Error: {evidence['error'].get('message', 'Unknown error')}")
        
        print(f"\nArtifacts: {latest_run}")
        print("=" * 60)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run OpenTDF BDD Tests")
    parser.add_argument("--tags", help="Run scenarios matching tags (e.g., '@smoke')")
    parser.add_argument("--profile", default="cross-sdk-basic", help="Test profile to use")
    parser.add_argument("--format", default="pretty", help="Output format (pretty, json, junit)")
    parser.add_argument("--install-deps", action="store_true", help="Install dependencies")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("OpenTDF BDD Test Runner")
    print("=" * 60)
    
    # Setup
    setup_environment()
    
    if args.install_deps:
        install_behave()
    
    # Check if behave is available
    try:
        import behave
    except ImportError:
        print("\nError: behave is not installed.")
        print("Run with --install-deps flag or install manually: pip install behave")
        return 1
    
    # Run tests
    print(f"\nProfile: {args.profile}")
    if args.tags:
        print(f"Tags: {args.tags}")
    
    exit_code = run_bdd_tests(
        tags=args.tags,
        profile=args.profile,
        format=args.format
    )
    
    # Generate summary
    artifacts_dir = Path(__file__).parent / "artifacts"
    generate_summary(artifacts_dir)
    
    # Exit with behave's exit code
    if exit_code == 0:
        print("\n✅ All tests passed!")
    else:
        print(f"\n❌ Tests failed with exit code {exit_code}")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())