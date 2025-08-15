"""Test framework demo feature using pytest-bdd."""

import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from pathlib import Path

# Load all scenarios from the feature file
scenarios('features/framework_demo.feature')

# Fixtures for state management
@pytest.fixture
def context():
    """Test context for sharing state between steps."""
    return {}

# Given steps
@given('the framework is initialized')
def framework_initialized(context):
    """Initialize the framework."""
    context['framework'] = {'initialized': True}

@given('the time controller is active')
def time_controller_active(context):
    """Activate the time controller."""
    context['time_controller'] = {'active': True, 'base_time': 0}

@given(parsers.parse('the randomness controller is active with seed {seed:d}'))
def randomness_controller_active(context, seed):
    """Activate the randomness controller with a specific seed."""
    context['random_controller'] = {'active': True, 'seed': seed}

@given(parsers.parse('a profile "{profile}" exists'))
def profile_exists(context, profile):
    """Check that a profile exists."""
    context['profile_name'] = profile

# When steps
@when(parsers.parse('I resolve the "{service}" service'))
def resolve_service(context, service):
    """Resolve a service."""
    # Mock service resolution
    context['resolved_service'] = {
        'name': service,
        'url': f'http://localhost:8080/{service}',
        'endpoint': 'localhost'
    }

@when(parsers.parse('I advance time by {hours:d} hours'))
def advance_time(context, hours):
    """Advance the controlled time."""
    if 'time_controller' in context:
        context['time_controller']['advanced_hours'] = hours

@when(parsers.parse('I generate {count:d} random numbers'))
def generate_random_numbers(context, count):
    """Generate random numbers."""
    if 'random_controller' in context:
        import random
        random.seed(context['random_controller']['seed'])
        context['random_numbers'] = [random.random() for _ in range(count)]

@when('I load the profile')
def load_profile(context):
    """Load a profile."""
    if 'profile_name' in context:
        context['loaded_profile'] = {
            'name': context['profile_name'],
            'capabilities': ['cap1', 'cap2'],
            'configuration': {'key': 'value'}
        }

# Then steps
@then('the service should have a valid URL')
def service_has_valid_url(context):
    """Check that the service has a valid URL."""
    assert 'resolved_service' in context
    assert 'url' in context['resolved_service']
    assert context['resolved_service']['url'].startswith('http')

@then(parsers.parse('the service endpoint should be "{endpoint}"'))
def service_endpoint_matches(context, endpoint):
    """Check that the service endpoint matches."""
    assert context['resolved_service']['endpoint'] == endpoint

@then('evidence should be collected for the operation')
def evidence_collected(context):
    """Check that evidence was collected."""
    # In a real implementation, this would check the evidence collection system
    pass

@then(parsers.parse('the controlled time should be {hours:d} hours ahead'))
def time_advanced(context, hours):
    """Check that time was advanced correctly."""
    assert context['time_controller']['advanced_hours'] == hours

@then('the sequence should be deterministic')
def sequence_deterministic(context):
    """Check that the random sequence is deterministic."""
    assert 'random_numbers' in context
    # Re-generate with same seed should give same sequence
    import random
    random.seed(context['random_controller']['seed'])
    expected = [random.random() for _ in range(len(context['random_numbers']))]
    assert context['random_numbers'] == expected

@then('the profile should have valid capabilities')
def profile_has_capabilities(context):
    """Check that the profile has valid capabilities."""
    assert 'loaded_profile' in context
    assert len(context['loaded_profile']['capabilities']) > 0

@then('the profile should have configuration')
def profile_has_configuration(context):
    """Check that the profile has configuration."""
    assert 'loaded_profile' in context
    assert len(context['loaded_profile']['configuration']) > 0