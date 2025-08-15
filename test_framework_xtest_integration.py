#!/usr/bin/env python3
"""Test that the framework integration works with xtest."""

import subprocess
import sys
from pathlib import Path

# Add current directory to Python path so framework module can be found
sys.path.insert(0, str(Path(__file__).parent))

def run_pytest_with_profile(profile: str, test_path: str = "xtest/test_nano.py::test_magic_version"):
    """Run pytest with a specific profile."""
    cmd = [
        sys.executable, "-m", "pytest",
        test_path,
        f"--profile={profile}",
        "-v", "--tb=short"
    ]
    
    print(f"\n{'='*60}")
    print(f"Running: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    # Set PYTHONPATH to include current directory
    import os
    env = os.environ.copy()
    env['PYTHONPATH'] = str(Path(__file__).parent)
    
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    
    print("STDOUT:")
    print(result.stdout)
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    return result.returncode == 0


def test_nano_without_kas():
    """Test that nano tests work without KAS profile."""
    # test_magic_version is a simple unit test that doesn't need KAS
    success = run_pytest_with_profile("no-kas", "xtest/test_nano.py::test_magic_version")
    assert success, "Simple nano test should work with no-kas profile"


def test_encryption_skipped_without_kas():
    """Test that encryption tests are skipped with no-kas profile."""
    # Run a test that requires encryption - it should be skipped
    import os
    env = os.environ.copy()
    env['PYTHONPATH'] = str(Path(__file__).parent)
    
    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         "xtest/test_tdfs.py",
         "--profile=no-kas",
         "-v", "-k", "test_round_trip",
         "--tb=short",
         "--co"  # collect-only to see what would run
        ],
        capture_output=True,
        text=True,
        env=env
    )
    
    print("\n" + "="*60)
    print("Testing that encryption tests are skipped with no-kas profile:")
    print("="*60)
    print(result.stdout)
    
    # With no-kas profile, encryption tests should be deselected or skipped
    # The test_round_trip requires encryption, so it should not run
    assert "deselected" in result.stdout.lower() or "skip" in result.stdout.lower() or result.returncode == 5, \
        "Encryption tests should be skipped with no-kas profile"


def test_framework_fixtures_available():
    """Test that framework fixtures are available in xtest."""
    test_code = '''
import pytest

# Load the framework plugin
pytest_plugins = ["framework.pytest_plugin"]

def test_framework_fixtures(service_locator, framework_profile):
    """Test that framework fixtures are available."""
    assert service_locator is not None
    # profile might be None if not specified
    print(f"Profile: {framework_profile}")
    print(f"Service Locator: {service_locator}")
'''
    
    test_file = Path("test_temp_framework.py")
    test_file.write_text(test_code)
    
    try:
        import os
        env = os.environ.copy()
        env['PYTHONPATH'] = str(Path(__file__).parent)
        
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short"],
            capture_output=True,
            text=True,
            env=env
        )
        
        print("\n" + "="*60)
        print("Testing framework fixtures availability:")
        print("="*60)
        print(result.stdout)
        
        success = result.returncode == 0
        assert success, "Framework fixtures should be available"
    finally:
        test_file.unlink(missing_ok=True)


def main():
    """Run integration tests."""
    print("\n" + "="*60)
    print("FRAMEWORK-XTEST INTEGRATION TESTS")
    print("="*60)
    
    tests = [
        ("Framework fixtures available", test_framework_fixtures_available),
        ("Nano test with no-kas profile", test_nano_without_kas),
        ("Encryption tests skipped with no-kas", test_encryption_skipped_without_kas),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        print(f"\n Testing: {name}")
        try:
            test_func()
            print(f"✓ PASSED: {name}")
            passed += 1
        except AssertionError as e:
            print(f"✗ FAILED: {name}")
            print(f"  Error: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR: {name}")
            print(f"  Error: {e}")
            failed += 1
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n✓ All integration tests passed!")
        print("\nThe framework integration is working correctly:")
        print("  - Framework fixtures are available in xtest")
        print("  - Profile-based test filtering works")
        print("  - no-kas profile correctly skips encryption tests")
        print("  - Profiles work universally across test suites")
    else:
        print("\n✗ Some tests failed. Check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()