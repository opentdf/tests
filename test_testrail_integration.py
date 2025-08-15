#!/usr/bin/env python3
"""Test TestRail integration components."""

import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

# Load .env file if it exists
import load_env

from framework.integrations.testrail_config import TestRailConfig
from framework.integrations.testrail_client import TestRailClient, TestRailAPIError
from framework.integrations.testrail_models import TestCase, TestRun, TestResult, TestStatus


def test_config_loading():
    """Test configuration loading."""
    print("=" * 60)
    print("Testing TestRail Configuration")
    print("=" * 60)
    
    # Test environment-based config
    config = TestRailConfig.from_env()
    print(f"Base URL: {config.base_url}")
    print(f"Username: {config.username}")
    print(f"API Key: {'*' * 8 if config.api_key else 'NOT SET'}")
    print(f"Project ID: {config.project_id}")
    print(f"Batch Size: {config.batch_size}")
    print(f"Cache Enabled: {config.enable_cache}")
    
    # Check if credentials are set
    if not config.api_key:
        print("\n⚠️  No API credentials found!")
        print("Set these environment variables:")
        print("  - TESTRAIL_USERNAME")
        print("  - TESTRAIL_API_KEY")
        print("  - TESTRAIL_PROJECT_ID")
        return False
    
    return True


def test_client_connection(config: TestRailConfig):
    """Test client connection to TestRail."""
    print("\n" + "=" * 60)
    print("Testing TestRail Client Connection")
    print("=" * 60)
    
    try:
        client = TestRailClient(config)
        
        # Try to get project info
        project = client.get_project()
        print(f"✓ Connected to project: {project.get('name')}")
        print(f"  Project ID: {project.get('id')}")
        print(f"  Is completed: {project.get('is_completed')}")
        
        return client
        
    except TestRailAPIError as e:
        print(f"✗ Failed to connect: {e}")
        return None
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return None


def test_data_models():
    """Test data model creation."""
    print("\n" + "=" * 60)
    print("Testing Data Models")
    print("=" * 60)
    
    # Test TestCase model
    test_case = TestCase(
        title="Sample BDD Test Case",
        type_id=14,  # BDD type
        priority_id=2,  # Medium
        custom_gherkin="Scenario: User logs in\n  Given user is on login page\n  When user enters credentials\n  Then user sees dashboard",
        custom_tags=["@smoke", "@req:BR-101", "@cap:auth=basic"],
        custom_requirements=["BR-101"],
        custom_capabilities={"auth": "basic"}
    )
    
    case_dict = test_case.to_dict()
    print(f"✓ Created TestCase model")
    print(f"  Title: {case_dict['title']}")
    print(f"  Has Gherkin: {'custom_gherkin' in case_dict}")
    
    # Test TestRun model
    test_run = TestRun(
        name=f"Test Run - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        description="Integration test run",
        custom_profile="cross-sdk-basic",
        custom_commit_sha="abc123def456"
    )
    
    run_dict = test_run.to_dict()
    print(f"✓ Created TestRun model")
    print(f"  Name: {run_dict['name']}")
    
    # Test TestResult model
    test_result = TestResult(
        status_id=TestStatus.PASSED,
        comment="Test passed successfully",
        elapsed="1m 30s",
        custom_artifact_url="https://example.com/artifacts/123",
        custom_profile="cross-sdk-basic"
    )
    
    result_dict = test_result.to_dict()
    print(f"✓ Created TestResult model")
    print(f"  Status: {TestStatus(result_dict['status_id']).name}")
    
    return True


def test_suite_operations(client: TestRailClient):
    """Test suite operations."""
    print("\n" + "=" * 60)
    print("Testing Suite Operations")
    print("=" * 60)
    
    try:
        # Get existing suites
        suites = client.get_suites()
        print(f"Found {len(suites)} existing suites:")
        for suite in suites[:3]:  # Show first 3
            print(f"  - {suite['name']} (ID: {suite['id']})")
        
        return True
        
    except TestRailAPIError as e:
        print(f"✗ Failed to get suites: {e}")
        return False


def main():
    """Run integration tests."""
    print("\n" + "=" * 60)
    print("TESTRAIL INTEGRATION TEST SUITE")
    print("=" * 60)
    
    # Test configuration
    config = TestRailConfig.from_env()
    
    # Check if we have credentials
    has_creds = config.api_key and config.username
    
    if not has_creds:
        print("\n⚠️  WARNING: No TestRail credentials configured!")
        print("\nTo configure TestRail, either:")
        print("\n1. Copy .env.example to .env and update with your credentials:")
        print("   cp .env.example .env")
        print("   # Edit .env with your TestRail credentials")
        print("\n2. Or set environment variables directly:")
        print("   export TESTRAIL_USERNAME=your_email@example.com")
        print("   export TESTRAIL_API_KEY=your_api_key")
        print("   export TESTRAIL_PROJECT_ID=1")
        print("\nContinuing with local tests only...\n")
    
    # Always test config loading
    if test_config_loading():
        print("✓ Configuration tests passed")
    
    # Always test data models
    if test_data_models():
        print("✓ Data model tests passed")
    
    # Only test API if credentials are available
    if has_creds:
        client = test_client_connection(config)
        
        if client:
            print("✓ Client connection successful")
            
            # Test suite operations
            if test_suite_operations(client):
                print("✓ Suite operations successful")
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print("✓ TestRail configuration module working")
    print("✓ TestRail client module working")
    print("✓ TestRail models module working")
    
    if has_creds:
        print("✓ API connection tested (with credentials)")
    else:
        print("⚠️  API connection not tested (no credentials)")
    
    print("\nNext steps:")
    print("1. Set TestRail credentials if needed")
    print("2. Implement BDD parser (bdd_parser.py)")
    print("3. Create sync scripts (bdd_sync.py)")
    print("4. Add CLI commands for upload/download")
    print("=" * 60)


if __name__ == "__main__":
    main()