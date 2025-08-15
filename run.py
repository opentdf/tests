import argparse
import os
import subprocess
import sys

def run_command(command, cwd=None, venv=False):
    """Run a shell command and exit if it fails."""
    if venv:
        command = ["source", ".venv/bin/activate", "&&"] + command
    print(f"Running command: {' '.join(command)}")
    # run with shell=True because of `source`
    result = subprocess.run(" ".join(command), cwd=cwd, shell=True, executable="/bin/bash")
    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)

def check_uv():
    """Check if uv is installed and install it if not."""
    try:
        subprocess.run(["uv", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("uv not found, installing it...")
        run_command(["pip", "install", "uv"])

def setup(args):
    """Set up the test environment."""
    print("Setting up the test environment...")
    check_uv()
    print("Creating virtual environment...")
    run_command(["uv", "venv"])
    print("Installing dependencies...")
    run_command(["uv", "pip", "sync", "requirements.txt"], venv=True)
    print("Checking out SDKs...")
    run_command(["./xtest/sdk/scripts/checkout-all.sh"])
    print("SDKs checked out successfully.")

def start(args):
    """Start the OpenTDF platform."""
    print("Starting the OpenTDF platform...")
    run_command(["docker-compose", "up", "-d"], cwd="xtest/platform")
    print("Platform started successfully.")

def stop(args):
    """Stop the OpenTDF platform."""
    print("Stopping the OpenTDF platform...")
    run_command(["docker-compose", "down"], cwd="xtest/platform")
    print("Platform stopped successfully.")

def test(args):
    """Run the specified test suite."""
    print(f"Running test suite: {args.suite}")

    if args.suite in ["xtest", "all"]:
        print("Running xtest suite...")
        pytest_cmd = ["pytest"]
        if args.profile:
            pytest_cmd.extend(["--profile", args.profile])
        if args.evidence:
            pytest_cmd.append("--evidence")
        if args.deterministic:
            pytest_cmd.append("--deterministic")
        if args.extra_args:
            pytest_cmd.extend(args.extra_args)
        run_command(pytest_cmd, cwd="xtest", venv=True)

    if args.suite in ["bdd", "all"]:
        print("Running BDD suite...")
        behave_cmd = ["behave"]
        if args.extra_args:
            behave_cmd.extend(args.extra_args)
        run_command(behave_cmd, cwd="bdd", venv=True)

    if args.suite in ["vulnerability", "all"]:
        print("Running vulnerability suite...")
        run_command(["npm", "install"], cwd="vulnerability")
        run_command(["npm", "test"], cwd="vulnerability")

def main():
    parser = argparse.ArgumentParser(description="A script to rule the OpenTDF tests.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Setup command
    parser_setup = subparsers.add_parser("setup", help="Set up the test environment.")
    parser_setup.set_defaults(func=setup)

    # Start command
    parser_start = subparsers.add_parser("start", help="Start the OpenTDF platform.")
    parser_start.set_defaults(func=start)

    # Stop command
    parser_stop = subparsers.add_parser("stop", help="Stop the OpenTDF platform.")
    parser_stop.set_defaults(func=stop)

    # Test command
    parser_test = subparsers.add_parser("test", help="Run the tests.")
    parser_test.add_argument("--suite", choices=["xtest", "bdd", "vulnerability", "all"], default="all", help="The test suite to run.")
    parser_test.add_argument("--profile", help="The profile to use for testing.")
    parser_test.add_argument("--evidence", action="store_true", help="Enable evidence collection.")
    parser_test.add_argument("--deterministic", action="store_true", help="Enable deterministic mode.")
    parser_test.add_argument("extra_args", nargs=argparse.REMAINDER, help="Additional arguments to pass to the test runner.")
    parser_test.set_defaults(func=test)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
