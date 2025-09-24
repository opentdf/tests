#!/usr/bin/env python3
"""
Performance comparison script: SDK servers vs CLI subprocess approach.

This script demonstrates the dramatic performance improvement achieved by
using SDK servers instead of subprocess calls.
"""

import time
import subprocess
import statistics
import os
from pathlib import Path


def run_test_suite(use_servers: bool, test_file: str = "test_tdfs.py") -> dict:
    """Run test suite with SDK servers enabled or disabled."""
    
    env = os.environ.copy()
    env["USE_SDK_SERVERS"] = "true" if use_servers else "false"
    
    # Run a subset of tests to measure performance
    cmd = [
        "pytest",
        test_file,
        "-k", "test_tdf_roundtrip",
        "--sdks", "go",  # Use only Go SDK for fair comparison
        "--containers", "ztdf",  # Test only ztdf format
        "-v",
        "--tb=short"
    ]
    
    print(f"\n{'='*60}")
    print(f"Running tests with SDK servers: {use_servers}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    start_time = time.time()
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    elapsed = time.time() - start_time
    
    # Parse test results
    passed = 0
    failed = 0
    for line in result.stdout.split('\n'):
        if 'passed' in line and 'failed' in line:
            # Parse pytest summary line
            parts = line.split()
            for i, part in enumerate(parts):
                if 'passed' in part and i > 0:
                    passed = int(parts[i-1])
                if 'failed' in part and i > 0:
                    failed = int(parts[i-1])
    
    return {
        'elapsed': elapsed,
        'passed': passed,
        'failed': failed,
        'success': result.returncode == 0
    }


def main():
    """Run performance comparison."""
    
    print("\n" + "="*70)
    print("OpenTDF Test Framework Performance Comparison")
    print("SDK Servers vs CLI Subprocess Approach")
    print("="*70)
    
    # Check if SDK servers are available
    try:
        import requests
        for port, sdk in [(8091, "Go"), (8092, "Java"), (8093, "JS")]:
            try:
                response = requests.get(f"http://localhost:{port}/health", timeout=1)
                if response.status_code == 200:
                    print(f"✅ {sdk} SDK server is running on port {port}")
            except:
                print(f"⚠️  {sdk} SDK server not available on port {port}")
    except ImportError:
        print("⚠️  requests module not available, skipping server health check")
    
    print("\nStarting performance comparison...")
    
    # Run tests with CLI approach (subprocess)
    print("\n1. Testing with CLI subprocess approach...")
    cli_result = run_test_suite(use_servers=False)
    
    # Run tests with SDK servers
    print("\n2. Testing with SDK server approach...")
    server_result = run_test_suite(use_servers=True)
    
    # Display results
    print("\n" + "="*70)
    print("PERFORMANCE RESULTS")
    print("="*70)
    
    print("\n📊 Test Execution Times:")
    print(f"  CLI Subprocess:  {cli_result['elapsed']:.2f} seconds")
    print(f"  SDK Servers:     {server_result['elapsed']:.2f} seconds")
    
    if cli_result['elapsed'] > 0 and server_result['elapsed'] > 0:
        improvement = cli_result['elapsed'] / server_result['elapsed']
        print(f"\n🚀 Performance Improvement: {improvement:.1f}x faster")
        
        time_saved = cli_result['elapsed'] - server_result['elapsed']
        print(f"⏰ Time Saved: {time_saved:.2f} seconds")
        
        # Extrapolate to full test suite
        print(f"\n💡 For a full test suite that takes 10 minutes with CLI:")
        print(f"   Would take only {10/improvement:.1f} minutes with SDK servers")
        print(f"   Saving {10 - 10/improvement:.1f} minutes per test run")
    
    print("\n📈 Test Results:")
    print(f"  CLI:     {cli_result['passed']} passed, {cli_result['failed']} failed")
    print(f"  Servers: {server_result['passed']} passed, {server_result['failed']} failed")
    
    if not cli_result['success']:
        print("\n⚠️  CLI tests had failures")
    if not server_result['success']:
        print("\n⚠️  Server tests had failures")
    
    print("\n" + "="*70)
    print("✅ Performance comparison complete")
    print("="*70)


if __name__ == "__main__":
    main()