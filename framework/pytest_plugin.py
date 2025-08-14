"""Universal pytest plugin for framework integration.

This plugin provides framework capabilities to any pytest-based test suite
including xtest, without requiring suite-specific configuration.
"""

import os
import json
import pytest
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

from framework.core import ProfileManager, ServiceLocator
from framework.utils import TimeController, RandomnessController


def pytest_addoption(parser):
    """Add framework-specific command line options."""
    parser.addoption(
        "--profile",
        default=None,
        help="Test profile to use (e.g., cross-sdk-basic, no-kas)",
    )
    parser.addoption(
        "--evidence",
        action="store_true",
        default=False,
        help="Enable evidence collection for test runs",
    )
    parser.addoption(
        "--deterministic",
        action="store_true",
        default=False,
        help="Enable deterministic mode (controlled time and randomness)",
    )


def pytest_configure(config):
    """Configure pytest with framework extensions."""
    # Add custom markers
    config.addinivalue_line(
        "markers", "req(id): mark test with requirement ID (e.g., BR-101)"
    )
    config.addinivalue_line(
        "markers", "cap(**kwargs): mark test with required capabilities"
    )
    
    # Initialize framework components
    profile_id = config.getoption("--profile")
    if profile_id:
        profiles_dir = Path(__file__).parent.parent / "profiles"
        config.framework_profile_manager = ProfileManager(profiles_dir)
        try:
            config.framework_profile = config.framework_profile_manager.load_profile(profile_id)
        except Exception as e:
            # If profile doesn't exist, continue without it
            config.framework_profile = None
            print(f"Warning: Could not load profile '{profile_id}': {e}")
    else:
        config.framework_profile = None
        config.framework_profile_manager = None
    
    # Initialize service locator
    config.framework_service_locator = ServiceLocator()
    
    # Initialize deterministic controls if requested
    if config.getoption("--deterministic"):
        config.framework_time_controller = TimeController()
        config.framework_time_controller.start()
        config.framework_randomness_controller = RandomnessController()
        config.framework_randomness_controller.start()
    
    # Initialize evidence collection if requested
    if config.getoption("--evidence"):
        config.framework_evidence_enabled = True
        config.framework_run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        artifacts_dir = Path("artifacts") / config.framework_run_id
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        config.framework_artifacts_dir = artifacts_dir
    else:
        config.framework_evidence_enabled = False


def pytest_collection_modifyitems(config, items):
    """Filter tests based on profile capabilities."""
    if not config.framework_profile:
        return
    
    profile = config.framework_profile
    deselected = []
    
    for item in items:
        # Check capability markers
        cap_marker = item.get_closest_marker("cap")
        if cap_marker:
            required_caps = cap_marker.kwargs
            
            # Special handling for no-kas profile
            if profile.id == "no-kas":
                # Skip any test that requires encryption capabilities
                if any(key in ["format", "encryption", "policy", "kas_type"] for key in required_caps):
                    deselected.append(item)
                    item.add_marker(pytest.mark.skip(
                        reason=f"Profile '{profile.id}' does not support encryption capabilities"
                    ))
                    continue
            
            # Standard capability checking
            for cap_key, cap_value in required_caps.items():
                if cap_key not in profile.capabilities:
                    deselected.append(item)
                    item.add_marker(pytest.mark.skip(
                        reason=f"Profile '{profile.id}' missing capability: {cap_key}"
                    ))
                    break
                
                if cap_value not in profile.capabilities[cap_key]:
                    deselected.append(item)
                    item.add_marker(pytest.mark.skip(
                        reason=f"Profile '{profile.id}' does not support {cap_key}={cap_value}"
                    ))
                    break
    
    # Remove deselected items
    for item in deselected:
        if item in items:
            items.remove(item)
    
    if deselected:
        config.hook.pytest_deselected(items=deselected)


@pytest.fixture(scope="session")
def framework_profile(pytestconfig):
    """Provide the current test profile."""
    return pytestconfig.framework_profile


@pytest.fixture(scope="session")
def profile_manager(pytestconfig):
    """Provide the profile manager."""
    return pytestconfig.framework_profile_manager


@pytest.fixture(scope="session")
def service_locator(pytestconfig):
    """Provide the service locator for dynamic endpoint resolution."""
    return pytestconfig.framework_service_locator


@pytest.fixture(scope="session")
def time_controller(pytestconfig):
    """Provide the time controller for deterministic testing."""
    return getattr(pytestconfig, "framework_time_controller", None)


@pytest.fixture(scope="session")
def randomness_controller(pytestconfig):
    """Provide the randomness controller for deterministic testing."""
    return getattr(pytestconfig, "framework_randomness_controller", None)


def pytest_runtest_setup(item):
    """Setup for each test item."""
    # Check if test should be skipped based on profile
    if hasattr(item.config, "framework_profile") and item.config.framework_profile:
        profile = item.config.framework_profile
        
        # Check for cap markers
        cap_marker = item.get_closest_marker("cap")
        if cap_marker:
            # This is handled in collection_modifyitems, but double-check here
            pass


def pytest_runtest_makereport(item, call):
    """Collect evidence after test execution."""
    if call.when == "call" and hasattr(item.config, "framework_evidence_enabled"):
        if item.config.framework_evidence_enabled:
            # Collect test evidence
            evidence = {
                "test_name": item.nodeid,
                "outcome": call.excinfo is None and "passed" or "failed",
                "duration": call.duration,
                "timestamp": datetime.now().isoformat(),
            }
            
            # Extract requirement ID if present
            req_marker = item.get_closest_marker("req")
            if req_marker:
                evidence["requirement_id"] = req_marker.args[0] if req_marker.args else None
            
            # Extract capabilities if present
            cap_marker = item.get_closest_marker("cap")
            if cap_marker:
                evidence["capabilities"] = cap_marker.kwargs
            
            # Extract profile info
            if hasattr(item.config, "framework_profile") and item.config.framework_profile:
                evidence["profile_id"] = item.config.framework_profile.id
            
            # Save evidence
            evidence_file = item.config.framework_artifacts_dir / f"{item.nodeid.replace('/', '_')}_evidence.json"
            evidence_file.parent.mkdir(parents=True, exist_ok=True)
            with open(evidence_file, "w") as f:
                json.dump(evidence, f, indent=2)


def pytest_sessionfinish(session, exitstatus):
    """Cleanup after test session."""
    # Stop deterministic controllers if they were started
    if hasattr(session.config, "framework_time_controller"):
        if session.config.framework_time_controller:
            session.config.framework_time_controller.stop()
    
    if hasattr(session.config, "framework_randomness_controller"):
        if session.config.framework_randomness_controller:
            session.config.framework_randomness_controller.stop()
    
    # Generate session summary if evidence was collected
    if hasattr(session.config, "framework_evidence_enabled"):
        if session.config.framework_evidence_enabled:
            summary = {
                "run_id": session.config.framework_run_id,
                "profile": session.config.framework_profile.id if session.config.framework_profile else None,
                "total_tests": session.testscollected,
                "exit_status": exitstatus,
                "timestamp": datetime.now().isoformat(),
            }
            
            summary_file = session.config.framework_artifacts_dir / "session_summary.json"
            with open(summary_file, "w") as f:
                json.dump(summary, f, indent=2)


def filter_sdks_by_profile(sdks: List[Any], profile: Any) -> List[Any]:
    """Filter SDKs based on profile capabilities.
    
    This is a helper function that can be used by test suites to filter
    their SDK lists based on the current profile's capabilities.
    """
    if not profile:
        return sdks
    
    # If profile has no SDK capabilities, return all
    if "sdk" not in profile.capabilities:
        return sdks
    
    # Filter SDKs based on profile
    allowed_sdks = profile.capabilities.get("sdk", [])
    return [sdk for sdk in sdks if str(sdk).split("-")[0] in allowed_sdks]