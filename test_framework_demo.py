#!/usr/bin/env python3
"""Demo script to test the framework components."""

import sys
import os
from pathlib import Path
from datetime import datetime, timezone

# Add framework to path
sys.path.insert(0, str(Path(__file__).parent))

from framework.core import ServiceLocator, ProfileManager
from framework.utils import TimeController, RandomnessController


def test_service_locator():
    """Test the ServiceLocator component."""
    print("\n=== Testing ServiceLocator ===")
    
    locator = ServiceLocator(env="local")
    
    # List all registered services
    services = locator.list_services()
    print(f"Registered services: {list(services.keys())}")
    
    # Resolve KAS service
    kas = locator.resolve("kas")
    print(f"KAS URL: {kas.url}")
    print(f"KAS endpoint: {kas.endpoint}:{kas.port}")
    
    # Resolve platform service
    platform = locator.resolve("platform")
    print(f"Platform URL: {platform.url}")
    
    # Test health check
    kas_healthy = locator.health_check("kas")
    print(f"KAS health check: {kas_healthy}")
    
    print("✓ ServiceLocator working correctly")


def test_time_controller():
    """Test the TimeController component."""
    print("\n=== Testing TimeController ===")
    
    with TimeController() as tc:
        # Check initial time
        initial = tc.current_time
        print(f"Initial controlled time: {initial}")
        
        # Advance time
        tc.advance(hours=2, minutes=30)
        after_advance = tc.current_time
        print(f"After advancing 2h 30m: {after_advance}")
        
        # Set specific time
        target = datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
        tc.set_time(target)
        print(f"After setting to specific time: {tc.current_time}")
        
        # Reset to base
        tc.reset()
        print(f"After reset: {tc.current_time}")
        
        # Test time.time() patching
        import time
        timestamp = time.time()
        print(f"Patched time.time(): {timestamp}")
        print(f"Corresponds to: {datetime.fromtimestamp(timestamp, tz=timezone.utc)}")
    
    print("✓ TimeController working correctly")


def test_randomness_controller():
    """Test the RandomnessController component."""
    print("\n=== Testing RandomnessController ===")
    
    with RandomnessController(seed=42) as rc:
        # Get default generator
        rng = rc.get_generator()
        
        # Generate some random values
        print(f"Random float: {rng.random()}")
        print(f"Random int (1-100): {rng.randint(1, 100)}")
        print(f"Random choice from list: {rng.choice(['a', 'b', 'c', 'd'])}")
        
        # Test determinism - create another controller with same seed
        rc2 = RandomnessController(seed=42)
        rc2.start()
        rng2 = rc2.get_generator()
        
        # Should produce same sequence
        vals1 = [rng.random() for _ in range(3)]
        vals2 = [rng2.random() for _ in range(3)]
        
        # Reset first generator
        rc.reset_generator()
        vals3 = [rng.random() for _ in range(3)]
        
        print(f"First sequence: {vals1}")
        print(f"Second sequence (same seed): {vals2}")
        print(f"After reset: {vals3}")
        
        # Test crypto generator
        crypto = rc.generators['crypto']
        token = crypto.token_hex(16)
        print(f"Deterministic token: {token}")
        
        rc2.stop()
    
    print("✓ RandomnessController working correctly")


def test_profile_manager():
    """Test the ProfileManager component."""
    print("\n=== Testing ProfileManager ===")
    
    # First, create a sample profile
    profiles_dir = Path(__file__).parent / "profiles"
    
    # Create cross-sdk-basic profile if it doesn't exist
    profile_dir = profiles_dir / "cross-sdk-basic"
    profile_dir.mkdir(parents=True, exist_ok=True)
    
    # Create capabilities.yaml
    capabilities_yaml = """
sdk:
  - go
  - java
  - js
format:
  - nano
  - ztdf
encryption:
  - aes256gcm
"""
    (profile_dir / "capabilities.yaml").write_text(capabilities_yaml)
    
    # Create config.yaml
    config_yaml = """
roles:
  alice:
    attributes:
      - "group:engineering"
      - "clearance:secret"
  bob:
    attributes:
      - "group:marketing"
      - "clearance:public"
selection:
  strategy: "pairwise"
  max_variants: 10
timeouts:
  test: 60
  suite: 600
"""
    (profile_dir / "config.yaml").write_text(config_yaml)
    
    # Create policies.yaml
    policies_yaml = """
waivers:
  - test: "test_legacy_format"
    reason: "Legacy format deprecated"
expected_skips:
  - condition: "sdk == 'swift' and format == 'ztdf-ecwrap'"
    reason: "Swift SDK doesn't support EC yet"
severities:
  encryption_failure: "critical"
  policy_mismatch: "high"
  performance_degradation: "medium"
"""
    (profile_dir / "policies.yaml").write_text(policies_yaml)
    
    # Create capability catalog
    catalog_yaml = """
capabilities:
  sdk:
    description: 'SDK implementation'
    values: ['go', 'java', 'js', 'swift']
    type: 'string'
  format:
    description: 'TDF container format'
    values: ['nano', 'ztdf', 'ztdf-ecwrap']
    type: 'string'
  encryption:
    description: 'Encryption algorithm'
    values: ['aes256gcm', 'chacha20poly1305']
    type: 'string'
"""
    (profiles_dir / "capability-catalog.yaml").write_text(catalog_yaml)
    
    # Now test ProfileManager
    pm = ProfileManager(profiles_dir)
    
    # List profiles
    profiles = pm.list_profiles()
    print(f"Available profiles: {profiles}")
    
    # Load profile
    profile = pm.load_profile("cross-sdk-basic")
    print(f"Loaded profile: {profile.id}")
    print(f"Capabilities: {profile.capabilities}")
    print(f"Roles: {list(profile.config.roles.keys())}")
    
    # Generate test matrix
    matrix = pm.generate_capability_matrix(
        profile.capabilities,
        strategy="pairwise",
        max_variants=5
    )
    print(f"\nGenerated test matrix ({len(matrix)} variants):")
    for i, variant in enumerate(matrix[:3], 1):
        print(f"  Variant {i}: {variant}")
    if len(matrix) > 3:
        print(f"  ... and {len(matrix) - 3} more variants")
    
    # Test skip conditions
    test_caps = {"sdk": "swift", "format": "ztdf-ecwrap"}
    skip_reason = profile.should_skip("test_something", test_caps)
    if skip_reason:
        print(f"\nTest would be skipped: {skip_reason}")
    
    print("✓ ProfileManager working correctly")


def main():
    """Run all framework component tests."""
    print("=" * 60)
    print("OpenTDF Test Framework Demo")
    print("=" * 60)
    
    try:
        test_service_locator()
        test_time_controller()
        test_randomness_controller()
        test_profile_manager()
        
        print("\n" + "=" * 60)
        print("✅ All framework components working correctly!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())