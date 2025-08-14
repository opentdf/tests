"""BDD test environment setup with framework integration."""

import os
import sys
from pathlib import Path
from datetime import datetime
import json
import logging

# Add framework to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from behave import fixture, use_fixture
from framework.core import ServiceLocator, ProfileManager
from framework.utils import TimeController, RandomnessController

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@fixture
def service_locator(context):
    """Setup service locator for BDD tests."""
    context.service_locator = ServiceLocator(env=os.getenv("TEST_ENV", "local"))
    yield context.service_locator


@fixture  
def time_controller(context):
    """Setup time control for deterministic testing."""
    context.time_controller = TimeController()
    context.time_controller.start()
    yield context.time_controller
    context.time_controller.stop()


@fixture
def randomness_controller(context):
    """Setup randomness control for deterministic testing."""
    seed = int(os.getenv("TEST_SEED", "42"))
    context.randomness_controller = RandomnessController(seed=seed)
    context.randomness_controller.start()
    yield context.randomness_controller
    context.randomness_controller.stop()


@fixture
def profile_manager(context):
    """Setup profile manager for test configuration."""
    profiles_dir = Path(__file__).parent.parent / "profiles"
    context.profile_manager = ProfileManager(profiles_dir)
    
    # Load profile from command line or default
    profile_id = context.config.userdata.get("profile", "cross-sdk-basic")
    try:
        context.profile = context.profile_manager.load_profile(profile_id)
        logger.info(f"Loaded profile: {profile_id}")
    except Exception as e:
        logger.warning(f"Could not load profile {profile_id}: {e}")
        context.profile = None
    
    yield context.profile_manager


def extract_tag(tags, prefix):
    """Extract tag value with given prefix."""
    for tag in tags:
        if tag.startswith(prefix):
            return tag[len(prefix):]
    return None


def extract_tags(tags, prefix):
    """Extract all tag values with given prefix."""
    values = []
    for tag in tags:
        if tag.startswith(prefix):
            values.append(tag[len(prefix):])
    return values


def generate_variant_id(row):
    """Generate variant ID from scenario outline row."""
    if not row:
        return "default"
    return "-".join(str(v) for v in row.values())


def scenario_to_result(scenario):
    """Convert scenario to test result object."""
    return {
        "name": scenario.name,
        "status": scenario.status.name if scenario.status else "skipped",
        "duration": scenario.duration if hasattr(scenario, 'duration') else 0,
        "tags": list(scenario.tags),
        "error": str(scenario.exception) if scenario.status == "failed" else None
    }


def before_all(context):
    """Global test setup."""
    # Setup framework fixtures
    use_fixture(service_locator, context)
    use_fixture(time_controller, context)
    use_fixture(randomness_controller, context)
    use_fixture(profile_manager, context)
    
    # Initialize test run metadata
    context.run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    context.artifacts_dir = Path(__file__).parent.parent / "artifacts" / context.run_id
    context.artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize evidence collection
    context.evidence_collection = []
    
    logger.info(f"Test run ID: {context.run_id}")
    logger.info(f"Artifacts directory: {context.artifacts_dir}")


def before_feature(context, feature):
    """Feature setup."""
    # Extract feature-level tags
    context.feature_req_id = extract_tag(feature.tags, "req:")
    logger.info(f"Starting feature: {feature.name} (BR: {context.feature_req_id})")


def before_scenario(context, scenario):
    """Scenario setup with profile binding."""
    # Extract scenario tags
    context.req_id = extract_tag(scenario.tags, "req:") or context.feature_req_id
    context.required_capabilities = {}
    
    # Parse capability tags from scenario
    for tag in scenario.tags:
        if tag.startswith("cap:"):
            cap_str = tag[4:]  # Remove "cap:" prefix
            if "=" in cap_str:
                key, value = cap_str.split("=", 1)
                context.required_capabilities[key] = value
    
    # Get profile capabilities
    profile_capabilities = {}
    if context.profile:
        profile_capabilities = context.profile.capabilities
    
    # Extract other tags
    context.risk_level = extract_tag(scenario.tags, "risk:")
    context.is_smoke = "smoke" in scenario.tags
    context.testrail_id = extract_tag(scenario.tags, "testrail:")
    context.jira_key = extract_tag(scenario.tags, "jira:")
    
    # Setup variant from scenario outline
    if hasattr(context, "active_outline"):
        context.variant = generate_variant_id(context.active_outline)
    else:
        context.variant = "default"
    
    # Check if scenario should be skipped based on capabilities
    if context.profile and context.required_capabilities:
        # Check if profile has all required capabilities
        profile_caps = context.profile.capabilities
        
        for cap_key, cap_value in context.required_capabilities.items():
            # Check if capability exists in profile
            if cap_key not in profile_caps:
                # Special case: if profile is no-kas and test requires encryption/format/policy
                if context.profile.id == "no-kas" and cap_key in ["format", "encryption", "policy"]:
                    scenario.skip(f"Capability '{cap_key}' not available without KAS")
                    logger.info(f"Skipping '{scenario.name}': {cap_key} requires KAS")
                    return
                else:
                    scenario.skip(f"Capability '{cap_key}' not available in profile")
                    logger.info(f"Skipping '{scenario.name}': missing capability {cap_key}")
                    return
            
            # Check if the specific value is supported
            profile_values = profile_caps[cap_key]
            if cap_value not in profile_values:
                scenario.skip(f"Capability {cap_key}={cap_value} not supported by profile")
                logger.info(f"Skipping '{scenario.name}': {cap_key}={cap_value} not in {profile_values}")
                return
    
    # Also check profile-specific skip policies
    if context.profile:
        skip_reason = context.profile.should_skip(scenario.name, context.required_capabilities)
        if skip_reason:
            scenario.skip(skip_reason)
            logger.info(f"Skipping scenario '{scenario.name}': {skip_reason}")
    
    # Initialize scenario evidence
    context.scenario_evidence = {
        "req_id": context.req_id,
        "profile_id": context.profile.id if context.profile else "unknown",
        "variant": context.variant,
        "capabilities": context.capabilities,
        "start_timestamp": datetime.utcnow().isoformat() + "Z",
        "scenario_name": scenario.name,
        "tags": list(scenario.tags)
    }
    
    logger.info(f"Starting scenario: {scenario.name} (variant: {context.variant})")


def after_scenario(context, scenario):
    """Collect evidence after scenario execution."""
    # Complete scenario evidence
    context.scenario_evidence.update({
        "end_timestamp": datetime.utcnow().isoformat() + "Z",
        "status": scenario.status.name if scenario.status else "skipped",
        "duration": scenario.duration if hasattr(scenario, 'duration') else 0
    })
    
    # Add error information if failed
    if scenario.status == "failed" and scenario.exception:
        context.scenario_evidence["error"] = {
            "type": type(scenario.exception).__name__,
            "message": str(scenario.exception),
            "traceback": scenario.exc_traceback if hasattr(scenario, 'exc_traceback') else None
        }
    
    # Save evidence to file
    evidence_dir = context.artifacts_dir / context.req_id / context.variant
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    evidence_file = evidence_dir / f"{scenario.name.replace(' ', '_')}_evidence.json"
    with open(evidence_file, 'w') as f:
        json.dump(context.scenario_evidence, f, indent=2)
    
    # Add to collection
    context.evidence_collection.append(context.scenario_evidence)
    
    logger.info(f"Completed scenario: {scenario.name} - {scenario.status.name}")
    logger.debug(f"Evidence saved to: {evidence_file}")


def after_feature(context, feature):
    """Feature cleanup."""
    logger.info(f"Completed feature: {feature.name}")


def after_all(context):
    """Global test cleanup and summary."""
    # Check if initialization was successful
    if not hasattr(context, 'run_id'):
        logger.error("Test run was not properly initialized")
        return
    
    # Generate run summary
    summary = {
        "run_id": context.run_id,
        "total_scenarios": len(context.evidence_collection),
        "passed": sum(1 for e in context.evidence_collection if e["status"] == "passed"),
        "failed": sum(1 for e in context.evidence_collection if e["status"] == "failed"),
        "skipped": sum(1 for e in context.evidence_collection if e["status"] == "skipped"),
        "evidence": context.evidence_collection
    }
    
    # Save summary
    summary_file = context.artifacts_dir / "run_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    # Print summary
    logger.info("=" * 60)
    logger.info(f"Test Run Summary (ID: {context.run_id})")
    logger.info(f"Total Scenarios: {summary['total_scenarios']}")
    logger.info(f"Passed: {summary['passed']}")
    logger.info(f"Failed: {summary['failed']}")
    logger.info(f"Skipped: {summary['skipped']}")
    logger.info(f"Artifacts saved to: {context.artifacts_dir}")
    logger.info("=" * 60)