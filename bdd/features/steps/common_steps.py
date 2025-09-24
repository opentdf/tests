"""Common step definitions for profile-based skipping."""

from behave import given, then
import logging

logger = logging.getLogger(__name__)


@given('the scenario should be skipped for no-kas profile')
def step_check_no_kas_skip(context):
    """Check if scenario should be skipped for no-kas profile."""
    if context.profile and context.profile.id == "no-kas":
        # Check if this is an encryption-related scenario
        scenario_name = context.scenario.name if hasattr(context, 'scenario') else ""
        
        skip_keywords = ['encrypt', 'decrypt', 'tdf', 'kas', 'policy', 'abac']
        should_skip = any(keyword in scenario_name.lower() for keyword in skip_keywords)
        
        if should_skip:
            context.scenario.skip("Encryption operations not available without KAS")
            logger.info(f"Skipping scenario for no-kas profile: {scenario_name}")


@given('the test requires KAS')
def step_requires_kas(context):
    """Mark that test requires KAS."""
    if context.profile and context.profile.id == "no-kas":
        context.scenario.skip("Test requires KAS - not available in no-kas profile")
        

@then('the test is skipped if no KAS available')  
def step_skip_if_no_kas(context):
    """Skip test if KAS is not available."""
    if context.profile:
        # Check if KAS is enabled in profile
        services = context.profile.config.__dict__.get('services', {})
        kas_enabled = services.get('kas', {}).get('enabled', True)
        
        if not kas_enabled:
            context.scenario.skip("KAS not available in current profile")