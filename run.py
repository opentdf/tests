#!.venv/bin/python3
import argparse
import subprocess
import sys
import os
import time

def run_command(command, cwd=None, venv=False, env=None, stream_output=False):
    """Run a shell command and exit if it fails."""
    print(f"Running command: {' '.join(command)}")
    
    # For pytest commands, stream output in real-time
    if stream_output or (len(command) > 0 and command[0] == "pytest"):
        # Don't use shell for streaming output
        if venv:
            # Prepend venv activation for non-shell mode
            import os
            venv_python = os.path.join(".venv", "bin", "python")
            if command[0] == "pytest":
                command = [venv_python, "-m"] + command
        
        result = subprocess.run(command, cwd=cwd, env=env)
    else:
        # Use shell mode for other commands (needed for source, etc.)
        cmd_str = " ".join(command)
        if venv:
            cmd_str = f"source .venv/bin/activate && {cmd_str}"
        result = subprocess.run(cmd_str, cwd=cwd, shell=True, executable="/bin/bash", env=env)
    
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

    # Create work directory for all temporary files
    print("Creating work directory...")
    import os
    os.makedirs("work", exist_ok=True)
    with open("work/README.md", "w") as f:
        f.write("""# Work Directory

This directory contains temporary files and build artifacts:

- Test execution temporary files (pytest)
- SDK build artifacts
- External process outputs
- Session-scoped shared artifacts

This directory is automatically cleaned with './run.py clean'
""")

    # Clone platform repository into work directory
    print("Setting up platform...")
    if not os.path.exists("work/platform"):
        print("Cloning platform repository...")
        run_command(["git", "clone", "https://github.com/opentdf/platform.git", "work/platform"])
    else:
        print("Platform directory already exists, pulling latest...")
        run_command(["git", "pull"], cwd="work/platform")
    
    # Generate KAS certificates if they don't exist
    print("Checking for KAS certificates...")
    if not os.path.exists("work/platform/kas-cert.pem") or not os.path.exists("work/platform/kas-ec-cert.pem"):
        print("Generating KAS certificates...")
        # The init-temp-keys.sh script creates a 'keys' directory relative to where it's run
        # We need to run it from work/platform so the keys end up in work/platform/keys
        run_command(["bash", ".github/scripts/init-temp-keys.sh"], cwd="work/platform")
        print("KAS certificates generated successfully")
    else:
        print("KAS certificates already exist")

    print("Checking out SDKs...")
    run_command(["./xtest/sdk/scripts/checkout-all.sh"])
    print("SDKs checked out successfully.")
    print("Building SDKs...")
    run_command(["make", "all"], cwd="xtest/sdk")
    print("SDKs built successfully.")
    
    # Build SDK servers
    print("Building SDK servers...")
    build_sdk_servers()
    print("SDK servers built successfully.")

def build_sdk_servers():
    """Build SDK servers for testing."""
    import os
    
    # Build Go SDK server if it exists
    go_server_dir = "xtest/sdk/go/server"
    if os.path.exists(f"{go_server_dir}/main.go"):
        print("  Building Go SDK server...")
        try:
            # Try to build with existing go.mod
            run_command(["go", "mod", "tidy"], cwd=go_server_dir)
            run_command(["go", "build", "-o", "server", "."], cwd=go_server_dir)
            print("  ✓ Go SDK server built")
        except Exception as e:
            print(f"  ⚠ Failed to build Go SDK server: {e}")
    
    # Build JavaScript SDK server if it exists
    js_server_dir = "xtest/sdk/js"
    if os.path.exists(f"{js_server_dir}/server.js"):
        print("  Building JavaScript SDK server...")
        try:
            run_command(["npm", "install"], cwd=js_server_dir)
            print("  ✓ JavaScript SDK server built")
        except Exception as e:
            print(f"  ⚠ Failed to build JavaScript SDK server: {e}")
    
    # Build Java SDK server if it exists
    java_server_dir = "xtest/sdk/java/server"
    if os.path.exists(f"{java_server_dir}/pom.xml"):
        print("  Building Java SDK server...")
        try:
            run_command(["mvn", "clean", "package"], cwd=java_server_dir)
            print("  ✓ Java SDK server built")
        except Exception as e:
            print(f"  ⚠ Failed to build Java SDK server: {e}")

def check_sdk_servers_running():
    """Check if SDK servers are already running."""
    import urllib.request
    import urllib.error
    
    ports = [8091, 8092, 8093]  # Go, Java, JS
    for port in ports:
        try:
            with urllib.request.urlopen(f"http://localhost:{port}/healthz", timeout=1) as response:
                if response.status == 200:
                    return True  # At least one server is running
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            pass
    return False

def start_sdk_servers(profile):
    """Start SDK servers for each language (Go, JS, Java)."""
    import subprocess
    import os
    
    servers_started = []
    
    # Start Go SDK server
    if os.environ.get("ENABLE_GO_SDK_SERVER", "true") == "true":
        print("Starting Go SDK server...")
        go_server_dir = "xtest/sdk/go/server"
        
        # Check if server binary exists
        if not os.path.exists(f"{go_server_dir}/server"):
            print("  Go SDK server not built, building now...")
            build_sdk_servers()
        
        # Start the server
        env = os.environ.copy()
        env["GO_SDK_PORT"] = "8091"
        env["PLATFORM_ENDPOINT"] = "http://localhost:8080"
        
        service_log = f"work/go_sdk_server_{profile}.log"
        with open(service_log, 'w') as log_file:
            process = subprocess.Popen(
                ["./server"],
                cwd=go_server_dir,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True
            )
        
        # Save the PID for later cleanup
        with open(f"work/go_sdk_server_{profile}.pid", 'w') as f:
            f.write(str(process.pid))
        
        # Wait for the server to be ready
        time.sleep(2)
        if wait_for_sdk_server(8091, "Go"):
            print("  ✓ Go SDK server is ready on port 8091")
            servers_started.append("go")
        else:
            print("  ✗ Go SDK server failed to start")
            print(f"  Check logs at: {service_log}")
    
    # Start JavaScript SDK server
    if os.environ.get("ENABLE_JS_SDK_SERVER", "true") == "true":
        print("Starting JavaScript SDK server...")
        js_server_file = "xtest/sdk/js/server.js"
        
        if os.path.exists(js_server_file):
            # Start the server
            env = os.environ.copy()
            env["TESTHELPER_PORT"] = "8093"
            env["PLATFORM_ENDPOINT"] = "http://localhost:8080"
            env["OIDC_ENDPOINT"] = "http://localhost:8888/auth"
            
            service_log = f"work/js_sdk_server_{profile}.log"
            with open(service_log, 'w') as log_file:
                process = subprocess.Popen(
                    ["node", "server.js", "--daemonize"],
                    cwd="xtest/sdk/js",
                    env=env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True
                )
            
            # Save the PID for later cleanup
            with open(f"work/js_sdk_server_{profile}.pid", 'w') as f:
                f.write(str(process.pid))
            
            # Wait for the server to be ready
            time.sleep(2)
            if wait_for_sdk_server(8093, "JavaScript"):
                print("  ✓ JavaScript SDK server is ready on port 8093")
                servers_started.append("js")
            else:
                print("  ✗ JavaScript SDK server failed to start")
                print(f"  Check logs at: {service_log}")
        else:
            print("  ⚠ JavaScript SDK server not found, skipping")
    
    # Start Java SDK server
    if os.environ.get("ENABLE_JAVA_SDK_SERVER", "true") == "true":
        print("Starting Java SDK server...")
        java_server_script = "xtest/sdk/java/start-server.sh"
        
        if os.path.exists(java_server_script):
            # Start the server
            env = os.environ.copy()
            env["JAVA_SDK_PORT"] = "8092"
            env["PLATFORM_ENDPOINT"] = "http://localhost:8080"
            env["OIDC_ENDPOINT"] = "http://localhost:8888/auth"
            
            service_log = f"work/java_sdk_server_{profile}.log"
            with open(service_log, 'w') as log_file:
                process = subprocess.Popen(
                    ["bash", java_server_script, "--daemonize"],
                    env=env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True
                )
            
            # Save the PID for later cleanup
            with open(f"work/java_sdk_server_{profile}.pid", 'w') as f:
                f.write(str(process.pid))
            
            # Wait for the server to be ready
            time.sleep(3)  # Java takes a bit longer to start
            if wait_for_sdk_server(8092, "Java"):
                print("  ✓ Java SDK server is ready on port 8092")
                servers_started.append("java")
            else:
                print("  ✗ Java SDK server failed to start")
                print(f"  Check logs at: {service_log}")
        else:
            print("  ⚠ Java SDK server script not found, skipping")
    
    if servers_started:
        print(f"SDK servers started: {', '.join(servers_started)}")
    else:
        print("No SDK servers were started")
    
    return servers_started

def wait_for_sdk_server(port, sdk_name, timeout=30):
    """Wait for an SDK server to be ready."""
    import urllib.request
    import urllib.error
    
    url = f"http://localhost:{port}/healthz"
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            pass
        time.sleep(1)
    
    return False

def wait_for_keycloak(timeout=120):
    """Wait for Keycloak to be ready."""
    import time
    import urllib.request
    import urllib.error
    import ssl
    import http.client

    # Create an SSL context that doesn't verify certificates (for local development)
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    keycloak_url = "http://localhost:8888/auth/"
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with urllib.request.urlopen(keycloak_url, timeout=2) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, 
                http.client.RemoteDisconnected, ConnectionResetError):
            # Keycloak is still starting up
            pass
        time.sleep(2)
    
    return False

def wait_for_platform(port, timeout=120):
    """Wait for platform services to be ready."""
    import time
    import urllib.request
    import urllib.error
    import ssl

    kas_url = f"http://localhost:{port}/healthz"
    keycloak_url = "https://localhost:8443/auth/"

    # Create SSL context that doesn't verify certificates
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    start_time = time.time()
    services_ready = {"kas": False, "keycloak": False}

    while time.time() - start_time < timeout:
        # Check KAS health
        if not services_ready["kas"]:
            try:
                with urllib.request.urlopen(kas_url, timeout=2) as response:
                    if response.status == 200:
                        services_ready["kas"] = True
                        print(f"  ✓ KAS is ready on port {port}")
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
                pass

        # Check Keycloak health
        if not services_ready["keycloak"]:
            try:
                with urllib.request.urlopen(keycloak_url, timeout=2, context=ssl_context) as response:
                    # Keycloak returns 302 redirect when ready
                    if response.status in [200, 302]:
                        services_ready["keycloak"] = True
                        print(f"  ✓ Keycloak is ready on port 8443")
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
                pass

        # If all services are ready, return success
        if all(services_ready.values()):
            return True

        # Wait a bit before checking again
        time.sleep(2)

    # Timeout reached
    print(f"Timeout waiting for services. Status: {services_ready}")
    return False

def start(args):
    """Start the OpenTDF platform for the specified profile."""
    import os
    import yaml

    profile = args.profile if args.profile else "cross-sdk-basic"

    # Load profile configuration
    profile_dir = f"profiles/{profile}"
    if not os.path.exists(profile_dir):
        print(f"Error: Profile '{profile}' not found in profiles/ directory")
        print(f"Available profiles: {', '.join([d for d in os.listdir('profiles/') if os.path.isdir(f'profiles/{d}')])}")
        sys.exit(1)

    # Load profile config to check if platform services are needed
    config_file = f"{profile_dir}/config.yaml"
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
    else:
        config = {}

    # Check if this profile needs platform services
    services = config.get('services', {})
    if services.get('kas', {}).get('enabled', True) == False:
        print(f"Profile '{profile}' configured for no-KAS operation, no platform services to start")
        return

    print(f"Starting OpenTDF platform for profile '{profile}'...")

    # Use the main platform directory
    platform_dir = "work/platform"

    # Check if platform directory exists
    if not os.path.exists(platform_dir):
        print(f"Error: Platform directory not found at {platform_dir}")
        print(f"Please run './run.py setup' first to set up the platform")
        sys.exit(1)

    # Copy profile-specific opentdf.yaml if it exists
    profile_opentdf = f"{profile_dir}/opentdf.yaml"
    if os.path.exists(profile_opentdf):
        print(f"Using profile-specific opentdf.yaml from {profile_opentdf}")
        run_command(["cp", profile_opentdf, f"{platform_dir}/opentdf.yaml"])
    elif not os.path.exists(f"{platform_dir}/opentdf.yaml"):
        # Use default development config if no opentdf.yaml exists
        print(f"Using default opentdf-dev.yaml configuration")
        run_command(["cp", f"{platform_dir}/opentdf-dev.yaml", f"{platform_dir}/opentdf.yaml"])

    # Start docker-compose with environment variables
    env = os.environ.copy()
    env["JAVA_OPTS_APPEND"] = ""  # Suppress warning
    env["OPENTDF_PROFILE"] = profile

    # Start docker-compose
    print(f"Starting docker-compose...")
    run_command(["docker-compose", "up", "-d"], cwd=platform_dir, env=env)

    # Build platform (if needed)
    print(f"Building platform services...")
    run_command(["go", "build", "-o", "opentdf-service", "./service"], cwd=platform_dir)

    # Wait for Keycloak to be ready before provisioning
    print(f"Waiting for Keycloak to be ready...")
    if not wait_for_keycloak():
        print(f"✗ Keycloak failed to start within timeout")
        print(f"Check docker logs with: docker-compose -f work/platform/docker-compose.yaml logs keycloak")
        sys.exit(1)
    print(f"✓ Keycloak is ready")

    # Provision Keycloak realm for this profile (if not already done)
    provisioning_marker = f"{platform_dir}/.provisioned_{profile}"
    if not os.path.exists(provisioning_marker):
        print(f"Provisioning Keycloak realm for profile '{profile}'...")
        # Create realm specific to this profile
        env["OPENTDF_REALM"] = profile.replace("-", "_")
        run_command(["go", "run", "./service", "provision", "keycloak"], cwd=platform_dir, env=env)

        # Add fixtures (sample attributes and metadata)
        print(f"Adding fixtures for profile '{profile}'...")
        run_command(["go", "run", "./service", "provision", "fixtures"], cwd=platform_dir, env=env)

        # Mark as provisioned
        with open(provisioning_marker, 'w') as f:
            f.write(f"Provisioned realm for {profile}\n")

    # Start platform service for this profile
    print(f"Starting platform service for profile '{profile}'...")
    env["OPENTDF_DB_NAME"] = f"opentdf_{profile.replace('-', '_')}"
    env["OPENTDF_REALM"] = profile.replace("-", "_")

    # Start the service using the compiled binary
    # Note: This needs to run in background, so we use subprocess.Popen
    service_log = f"work/platform_service_{profile}.log"
    with open(service_log, 'w') as log_file:
        service_process = subprocess.Popen(
            ["./opentdf-service", "start"],
            cwd=platform_dir,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True
        )

    # Give the service a moment to start
    time.sleep(5)

    # Verify platform service is running
    print(f"Verifying platform service is ready...")
    if wait_for_platform(8080):
        print(f"✓ Platform for profile '{profile}' is fully ready")
        # Save the service PID for later cleanup
        with open(f"work/platform_service_{profile}.pid", 'w') as f:
            f.write(str(service_process.pid))
    else:
        print(f"✗ Platform service for profile '{profile}' failed to start")
        print(f"Check logs at: {service_log}")
        sys.exit(1)

    # Export environment for tests to use
    env_file = f"work/profile_{profile}.env"
    with open(env_file, 'w') as f:
        f.write(f"PLATFORM_DIR={os.path.abspath(platform_dir)}\n")
        f.write(f"PLATFORM_PORT=8080\n")
        f.write(f"KEYCLOAK_PORT=8081\n")
        f.write(f"POSTGRES_PORT=5432\n")
        f.write(f"PROFILE={profile}\n")
    print(f"Environment exported to {env_file}")

    # Start SDK servers if enabled
    if os.environ.get("USE_SDK_SERVERS", "true") == "true":
        print("Starting SDK servers...")
        start_sdk_servers(profile)

    print(f"Platform started successfully.")

def stop(args):
    """Stop the OpenTDF platform."""
    import os
    import signal
    import glob

    # Stop any running platform services
    print("Stopping platform services...")
    for pid_file in glob.glob("work/platform_service_*.pid"):
        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            print(f"Stopping platform service (PID: {pid})...")
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                print(f"Process {pid} not found (already stopped)")
            os.remove(pid_file)
        except Exception as e:
            print(f"Error stopping service from {pid_file}: {e}")
    
    # Stop SDK servers
    for pattern in ["work/go_sdk_server_*.pid", "work/js_sdk_server_*.pid", "work/java_sdk_server_*.pid"]:
        for pid_file in glob.glob(pattern):
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                server_type = os.path.basename(pid_file).split('_')[0].upper()
                print(f"Stopping {server_type} SDK server (PID: {pid})...")
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    print(f"Process {pid} not found (already stopped)")
                os.remove(pid_file)
            except Exception as e:
                print(f"Error stopping SDK server from {pid_file}: {e}")

    # Stop docker-compose
    platform_dir = "work/platform"
    if os.path.exists(platform_dir):
        print(f"Stopping docker-compose services...")
        run_command(["docker-compose", "down"], cwd=platform_dir)
        print(f"Docker services stopped.")
    else:
        print(f"Platform directory not found at {platform_dir}")

    print(f"Platform stopped successfully.")

def test(args):
    """Run the specified test suite."""
    import os
    
    print(f"Running test suite: {args.suite}")
    
    # Start SDK servers if needed for xtest suite (optional for now)
    if args.suite in ["xtest", "all"]:
        if os.environ.get("USE_SDK_SERVERS", "false").lower() == "true":
            print("Checking SDK servers...")
            profile = args.profile if hasattr(args, 'profile') and args.profile else "default"
            if not check_sdk_servers_running():
                print("Starting SDK servers for testing...")
                try:
                    start_sdk_servers(profile)
                except Exception as e:
                    print(f"Warning: Failed to start SDK servers: {e}")
                    print("Continuing without SDK servers...")
            else:
                print("SDK servers already running")
        else:
            print("SDK servers disabled (set USE_SDK_SERVERS=true to enable)")

    # Build pytest command
    pytest_cmd = ["pytest"]

    # Add parallel execution by default
    if args.parallel:
        # Use number of CPU cores if not specified
        if args.parallel == "auto":
            pytest_cmd.extend(["-n", "auto"])
        else:
            pytest_cmd.extend(["-n", str(args.parallel)])

    if args.profile:
        pytest_cmd.extend(["--profile", args.profile])
    if args.evidence:
        pytest_cmd.append("--evidence")
    if args.deterministic:
        pytest_cmd.append("--deterministic")
    if args.extra_args:
        pytest_cmd.extend(args.extra_args)

    # Determine which test directories to include
    if args.suite == "xtest":
        print("Running xtest suite...")
        pytest_cmd.append("xtest")
    elif args.suite == "bdd":
        print("Running BDD suite...")
        # BDD now uses pytest-bdd
        pytest_cmd.append("bdd")
    elif args.suite == "vulnerability":
        print("Running vulnerability suite...")
        run_command(["npm", "install"], cwd="vulnerability")
        run_command(["npm", "test"], cwd="vulnerability")
        return
    elif args.suite == "all":
        # Run both xtest and bdd with pytest in parallel
        # pytest-xdist will handle parallelization across both directories
        pytest_cmd.extend(["xtest", "bdd"])
        print("Running xtest and bdd suites in parallel with pytest...")
        run_command(pytest_cmd, venv=True)

        # Run vulnerability tests separately as they use npm
        print("\nRunning vulnerability suite...")
        run_command(["npm", "install"], cwd="vulnerability")
        run_command(["npm", "test"], cwd="vulnerability")
        return
    else:
        print(f"Unknown test suite: {args.suite}")
        sys.exit(1)

    # Run pytest with the specified directories
    run_command(pytest_cmd, venv=True)

def clean(args):
    """Clean up the test environment."""
    print("Cleaning up the test environment...")
    import os

    # Stop all platforms first
    print("Stopping all OpenTDF platforms...")
    if os.path.exists("work"):
        import glob
        platform_dirs = glob.glob("work/platform*")
        for platform_dir in platform_dirs:
            if os.path.isdir(platform_dir):
                print(f"Stopping platform in {platform_dir}...")
                try:
                    # Check if override file exists
                    compose_override = f"{platform_dir}/docker-compose.override.yml"
                    if os.path.exists(compose_override):
                        run_command(["docker-compose", "-f", "docker-compose.yaml", "-f", "docker-compose.override.yml", "down", "-v"],
                                   cwd=platform_dir)
                    else:
                        run_command(["docker-compose", "down", "-v"], cwd=platform_dir)
                except SystemExit:
                    print(f"Platform in {platform_dir} was not running or failed to stop cleanly.")
    else:
        print("Work directory not found, skipping platform shutdown...")

    # Remove work and pytest temporary directories
    print("Removing work and temporary directories...")
    if os.path.exists("work"):
        run_command(["rm", "-rf", "work"])  # At project root
    if os.path.exists(".pytest_cache"):
        run_command(["rm", "-rf", ".pytest_cache"])
    if os.path.exists("xtest/.pytest_cache"):
        run_command(["rm", "-rf", "xtest/.pytest_cache"])

    # Remove old tmp directory if it exists (from before migration)
    if os.path.exists("xtest/tmp"):
        run_command(["rm", "-rf", "xtest/tmp"])

    # Clean SDK build artifacts
    print("Cleaning SDK build artifacts...")
    if os.path.exists("xtest/sdk"):
        try:
            run_command(["make", "clean"], cwd="xtest/sdk")
        except SystemExit:
            print("SDK clean failed or Makefile not found.")

        # Also clean Maven target directories
        if os.path.exists("xtest/sdk"):
            run_command(["find", "xtest/sdk", "-type", "d", "-name", "target", "-exec", "rm", "-rf", "{}", "+"])

        # Remove SDK dist directories
        for sdk_dist in ["xtest/sdk/go/dist", "xtest/sdk/java/dist", "xtest/sdk/js/dist"]:
            if os.path.exists(sdk_dist):
                run_command(["rm", "-rf", sdk_dist])

    # Remove common generated files and directories, but NOT uncommitted source files
    print("Removing generated files and build artifacts...")
    
    # Remove Python cache directories
    run_command(["find", ".", "-type", "d", "-name", "__pycache__", "-exec", "rm", "-rf", "{}", "+"])
    run_command(["find", ".", "-type", "d", "-name", "*.egg-info", "-exec", "rm", "-rf", "{}", "+"])
    
    # Remove compiled files
    run_command(["find", ".", "-type", "f", "-name", "*.pyc", "-delete"])
    run_command(["find", ".", "-type", "f", "-name", "*.pyo", "-delete"])
    run_command(["find", ".", "-type", "f", "-name", "*.so", "-delete"])
    
    # Remove test artifacts
    for pattern in ["*.log", "*.pid", "*.tmp", ".coverage", "htmlcov"]:
        run_command(["find", ".", "-name", pattern, "-exec", "rm", "-rf", "{}", "+"])
    
    # Note: We do NOT use git clean -fdx because it would remove uncommitted source files
    # Users should manually run 'git clean -fdx' if they want to remove ALL untracked files

    print("Environment cleaned successfully.")

def main():
    parser = argparse.ArgumentParser(description="A script to rule the OpenTDF tests.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Setup command
    parser_setup = subparsers.add_parser("setup", help="Set up the test environment.")
    parser_setup.set_defaults(func=setup)

    # Start command
    parser_start = subparsers.add_parser("start", help="Start the OpenTDF platform for a specific profile.")
    parser_start.add_argument("--profile", default="cross-sdk-basic",
                             help="Profile from profiles/ directory to use (default: cross-sdk-basic)")
    parser_start.set_defaults(func=start)

    # Stop command
    parser_stop = subparsers.add_parser("stop", help="Stop the OpenTDF platform.")
    parser_stop.set_defaults(func=stop)

    # Test command
    parser_test = subparsers.add_parser("test", help="Run the tests.")
    parser_test.add_argument("suite", nargs="?", choices=["xtest", "bdd", "vulnerability", "all"], default="xtest", help="The test suite to run (default: xtest).")
    parser_test.add_argument("-n", "--parallel", nargs="?", const="auto", default="auto",
                           help="Run tests in parallel. Use 'auto' for automatic CPU detection, or specify number of workers (default: auto)")
    parser_test.add_argument("--no-parallel", dest="parallel", action="store_false",
                           help="Disable parallel test execution")
    parser_test.add_argument("--profile", help="The profile to use for testing.")
    parser_test.add_argument("--evidence", action="store_true", help="Enable evidence collection.")
    parser_test.add_argument("--deterministic", action="store_true", help="Enable deterministic mode.")
    parser_test.add_argument("extra_args", nargs=argparse.REMAINDER, help="Additional arguments to pass to the test runner.")
    parser_test.set_defaults(func=test)

    # Clean command
    parser_clean = subparsers.add_parser("clean", help="Clean up the test environment.")
    parser_clean.set_defaults(func=clean)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
