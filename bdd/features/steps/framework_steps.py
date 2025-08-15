"""Step definitions for framework demo features."""

from behave import given, when, then
import time


@given('the framework is initialized')
def step_framework_initialized(context):
    """Verify framework is initialized."""
    assert context.service_locator is not None, "Service locator not initialized"
    assert context.time_controller is not None, "Time controller not initialized"
    assert context.randomness_controller is not None, "Randomness controller not initialized"
    assert context.profile_manager is not None, "Profile manager not initialized"
    
    context.framework_initialized = True


@given('the time controller is active')
def step_time_controller_active(context):
    """Verify time controller is active."""
    assert context.time_controller._started, "Time controller not started"
    context.initial_time = context.time_controller.current_time


@given('the randomness controller is active with seed {seed:d}')
def step_randomness_controller_active(context, seed):
    """Verify randomness controller is active with specific seed."""
    assert context.randomness_controller._started, "Randomness controller not started"
    assert context.randomness_controller.seed == seed, f"Seed mismatch: expected {seed}, got {context.randomness_controller.seed}"


@given('a profile "{profile_name}" exists')
def step_profile_exists(context, profile_name):
    """Check if profile exists."""
    profiles = context.profile_manager.list_profiles()
    if profile_name not in profiles:
        # Create the profile for demo
        from pathlib import Path
        profile_dir = context.profile_manager.profiles_dir / profile_name
        profile_dir.mkdir(parents=True, exist_ok=True)
        
        # Create minimal profile files
        (profile_dir / "capabilities.yaml").write_text("sdk: [go, java]\nformat: [nano]")
        (profile_dir / "config.yaml").write_text("timeouts:\n  test: 60")
        (profile_dir / "policies.yaml").write_text("severities:\n  default: medium")
    
    context.profile_name = profile_name


@when('I resolve the "{service_name}" service')
def step_resolve_service(context, service_name):
    """Resolve a service using ServiceLocator."""
    try:
        context.resolved_service = context.service_locator.resolve(service_name)
        context.resolution_success = True
    except Exception as e:
        context.resolution_error = str(e)
        context.resolution_success = False


@when('I advance time by {hours:d} hours')
def step_advance_time(context, hours):
    """Advance controlled time."""
    context.time_controller.advance(hours=hours)
    context.advanced_time = context.time_controller.current_time


@when('I generate {count:d} random numbers')
def step_generate_random_numbers(context, count):
    """Generate random numbers using randomness controller."""
    rng = context.randomness_controller.get_generator()
    context.random_sequence = [rng.random() for _ in range(count)]


@when('I load the profile')
def step_load_profile(context):
    """Load a profile using ProfileManager."""
    try:
        context.loaded_profile = context.profile_manager.load_profile(context.profile_name)
        context.profile_load_success = True
    except Exception as e:
        context.profile_load_error = str(e)
        context.profile_load_success = False


@then('the service should have a valid URL')
def step_verify_service_url(context):
    """Verify service has valid URL."""
    assert context.resolution_success, f"Service resolution failed: {getattr(context, 'resolution_error', 'Unknown error')}"
    assert context.resolved_service is not None, "No service resolved"
    assert context.resolved_service.url, "Service has no URL"
    
    # Add to evidence
    context.scenario_evidence['service_resolution'] = {
        "service": context.resolved_service.name,
        "url": context.resolved_service.url,
        "success": True
    }


@then('the service endpoint should be "{expected_endpoint}"')
def step_verify_service_endpoint(context, expected_endpoint):
    """Verify service endpoint matches expected value."""
    assert context.resolved_service.endpoint == expected_endpoint, \
        f"Expected endpoint '{expected_endpoint}', got '{context.resolved_service.endpoint}'"


@then('the controlled time should be {hours:d} hours ahead')
def step_verify_time_advance(context, hours):
    """Verify time was advanced correctly."""
    from datetime import timedelta
    expected_time = context.initial_time + timedelta(hours=hours)
    actual_time = context.advanced_time
    
    # Allow small tolerance for floating point
    time_diff = abs((expected_time - actual_time).total_seconds())
    assert time_diff < 1, f"Time mismatch: expected {expected_time}, got {actual_time}"
    
    # Add to evidence
    context.scenario_evidence['time_control'] = {
        "initial": context.initial_time.isoformat(),
        "advanced": context.advanced_time.isoformat(),
        "hours_advanced": hours
    }


@then('the sequence should be deterministic')
def step_verify_deterministic_sequence(context):
    """Verify random sequence is deterministic."""
    # Generate the same sequence with a new controller using same seed
    from framework.utils import RandomnessController
    
    rc2 = RandomnessController(seed=42)
    rc2.start()
    rng2 = rc2.get_generator()
    expected_sequence = [rng2.random() for _ in range(len(context.random_sequence))]
    rc2.stop()
    
    assert context.random_sequence == expected_sequence, \
        f"Sequences don't match:\nGot:      {context.random_sequence}\nExpected: {expected_sequence}"
    
    # Add to evidence
    context.scenario_evidence['randomness_control'] = {
        "seed": 42,
        "sequence": context.random_sequence,
        "deterministic": True
    }


@then('the profile should have valid capabilities')
def step_verify_profile_capabilities(context):
    """Verify profile has valid capabilities."""
    assert context.profile_load_success, f"Profile load failed: {getattr(context, 'profile_load_error', 'Unknown error')}"
    assert context.loaded_profile is not None, "No profile loaded"
    assert context.loaded_profile.capabilities, "Profile has no capabilities"
    
    # Add to evidence
    context.scenario_evidence['profile'] = {
        "id": context.loaded_profile.id,
        "capabilities": context.loaded_profile.capabilities,
        "loaded": True
    }


@then('the profile should have configuration')
def step_verify_profile_config(context):
    """Verify profile has configuration."""
    assert context.loaded_profile.config is not None, "Profile has no configuration"
    assert context.loaded_profile.policies is not None, "Profile has no policies"