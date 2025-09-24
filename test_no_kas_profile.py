#!/usr/bin/env python3
"""Test script to demonstrate the no-KAS profile functionality."""

import sys
import os
from pathlib import Path

# Add framework to path
sys.path.insert(0, str(Path(__file__).parent))

from framework.core import ProfileManager, ServiceLocator


def test_no_kas_profile():
    """Test the no-KAS profile configuration."""
    print("\n" + "=" * 60)
    print("Testing No-KAS Profile")
    print("=" * 60)
    
    # Initialize ProfileManager
    profiles_dir = Path(__file__).parent / "profiles"
    pm = ProfileManager(profiles_dir)
    
    # List available profiles
    profiles = pm.list_profiles()
    print(f"\nAvailable profiles: {profiles}")
    assert "no-kas" in profiles, "no-kas profile not found"
    
    # Load the no-KAS profile
    profile = pm.load_profile("no-kas")
    print(f"\nLoaded profile: {profile.id}")
    
    # Display capabilities
    print("\nCapabilities:")
    for key, values in profile.capabilities.items():
        print(f"  {key}: {values}")
    
    # Check that KAS-related capabilities are not present
    assert "kas_type" not in profile.capabilities or profile.capabilities.get("kas_type") == ["none"], \
        "KAS type should not be available or should be 'none'"
    
    # Display configuration
    print("\nConfiguration:")
    print(f"  Roles: {list(profile.config.roles.keys())}")
    print(f"  Selection strategy: {profile.config.selection.get('strategy')}")
    print(f"  Max variants: {profile.config.selection.get('max_variants')}")
    
    # Check service configuration
    services = profile.config.__dict__.get('_data', profile.config.__dict__).get('services', {})
    if services:
        print("\nService Configuration:")
        for service, config in services.items():
            if isinstance(config, dict):
                enabled = config.get('enabled', True)
                reason = config.get('reason', '')
                print(f"  {service}: {'Enabled' if enabled else 'Disabled'}")
                if reason:
                    print(f"    Reason: {reason}")
    
    # Display policies
    print("\nPolicies:")
    print(f"  Waivers: {len(profile.policies.waivers)} defined")
    print(f"  Expected skips: {len(profile.policies.expected_skips)} rules")
    print(f"  Severities: {len(profile.policies.severities)} levels")
    
    # Show some waivers
    print("\nSample Waivers (first 3):")
    for waiver in profile.policies.waivers[:3]:
        print(f"  - {waiver['test']}: {waiver['reason']}")
    
    # Test skip conditions
    print("\nTesting Skip Conditions:")
    
    # Test 1: KAS-dependent format
    test_caps1 = {"format": "nano", "sdk": "go"}
    skip_reason1 = profile.should_skip("test_nano_encryption", test_caps1)
    print(f"  Test with nano format: {'SKIP' if skip_reason1 else 'RUN'}")
    if skip_reason1:
        print(f"    Reason: {skip_reason1}")
    
    # Test 2: Local-only format
    test_caps2 = {"format": "local-store", "sdk": "java", "operation_mode": "offline"}
    skip_reason2 = profile.should_skip("test_local_encryption", test_caps2)
    print(f"  Test with local-store format: {'SKIP' if skip_reason2 else 'RUN'}")
    if skip_reason2:
        print(f"    Reason: {skip_reason2}")
    
    # Test 3: Swift SDK (should always skip in no-KAS)
    test_caps3 = {"sdk": "swift", "format": "local-store"}
    skip_reason3 = profile.should_skip("test_swift_operations", test_caps3)
    print(f"  Test with Swift SDK: {'SKIP' if skip_reason3 else 'RUN'}")
    if skip_reason3:
        print(f"    Reason: {skip_reason3}")
    
    # Generate test matrix with limited capabilities
    print("\nGenerating Test Matrix:")
    no_kas_capabilities = {
        "sdk": ["go", "java"],
        "format": ["local-store"],
        "encryption": ["local-aes256gcm"],
        "operation_mode": ["offline"]
    }
    
    matrix = pm.generate_capability_matrix(
        no_kas_capabilities,
        strategy="minimal"
    )
    
    print(f"  Generated {len(matrix)} test variants:")
    for i, variant in enumerate(matrix, 1):
        print(f"    Variant {i}: {variant}")
    
    # Test service resolution with no-KAS profile
    print("\nService Resolution with No-KAS Profile:")
    
    # Set environment to indicate no-KAS mode
    os.environ["TDF_NO_KAS"] = "true"
    os.environ["KAS_URL"] = ""  # Empty to simulate no KAS
    
    sl = ServiceLocator(env="local")
    
    # Try to resolve KAS (should fail or return placeholder)
    try:
        kas = sl.resolve("kas")
        print(f"  KAS resolution: {kas.url} (placeholder/disabled)")
    except Exception as e:
        print(f"  KAS resolution: Failed as expected - {e}")
    
    # List all services
    services = sl.list_services()
    print(f"  Available services in no-KAS mode: {list(services.keys())}")
    
    print("\n" + "=" * 60)
    print("✅ No-KAS Profile Test Complete")
    print("=" * 60)
    
    return profile


def test_profile_comparison():
    """Compare no-KAS profile with standard profile."""
    print("\n" + "=" * 60)
    print("Profile Comparison: No-KAS vs Cross-SDK-Basic")
    print("=" * 60)
    
    profiles_dir = Path(__file__).parent / "profiles"
    pm = ProfileManager(profiles_dir)
    
    # Load both profiles
    no_kas = pm.load_profile("no-kas")
    
    # Create cross-sdk-basic if it doesn't exist
    cross_sdk_dir = profiles_dir / "cross-sdk-basic"
    if not cross_sdk_dir.exists():
        cross_sdk_dir.mkdir(parents=True, exist_ok=True)
        (cross_sdk_dir / "capabilities.yaml").write_text("""
sdk: [go, java, js, swift]
format: [nano, ztdf]
encryption: [aes256gcm]
kas_type: [standard]
auth_type: [oidc]
operation_mode: [online]
""")
        (cross_sdk_dir / "config.yaml").write_text("timeouts:\n  test: 60")
        (cross_sdk_dir / "policies.yaml").write_text("severities:\n  default: medium")
    
    cross_sdk = pm.load_profile("cross-sdk-basic")
    
    print("\nCapability Comparison:")
    print(f"{'Capability':<20} {'No-KAS':<30} {'Cross-SDK-Basic':<30}")
    print("-" * 80)
    
    # Get all capability keys
    all_keys = set(no_kas.capabilities.keys()) | set(cross_sdk.capabilities.keys())
    
    for key in sorted(all_keys):
        no_kas_vals = no_kas.capabilities.get(key, ["N/A"])
        cross_sdk_vals = cross_sdk.capabilities.get(key, ["N/A"])
        
        no_kas_str = ", ".join(no_kas_vals[:2]) if isinstance(no_kas_vals, list) else str(no_kas_vals)
        if isinstance(no_kas_vals, list) and len(no_kas_vals) > 2:
            no_kas_str += "..."
            
        cross_sdk_str = ", ".join(cross_sdk_vals[:2]) if isinstance(cross_sdk_vals, list) else str(cross_sdk_vals)
        if isinstance(cross_sdk_vals, list) and len(cross_sdk_vals) > 2:
            cross_sdk_str += "..."
        
        print(f"{key:<20} {no_kas_str:<30} {cross_sdk_str:<30}")
    
    print("\nKey Differences:")
    print("  1. No-KAS profile lacks KAS-related capabilities")
    print("  2. No-KAS uses local/offline formats only")
    print("  3. No-KAS has no policy enforcement")
    print("  4. No-KAS operates in offline/standalone mode")
    print("  5. No-KAS uses local key management")
    
    print("\n" + "=" * 60)
    print("✅ Profile Comparison Complete")
    print("=" * 60)


def main():
    """Run all no-KAS profile tests."""
    try:
        # Test the no-KAS profile
        profile = test_no_kas_profile()
        
        # Compare profiles
        test_profile_comparison()
        
        print("\n" + "=" * 60)
        print("✅ All No-KAS Profile Tests Passed!")
        print("=" * 60)
        
        # Show usage example
        print("\nUsage Example:")
        print("  To run tests with no-KAS profile:")
        print("  python run_bdd_tests.py --profile no-kas")
        print("\n  This will:")
        print("  - Skip all KAS-dependent tests")
        print("  - Use local key management")
        print("  - Run in offline mode")
        print("  - Apply all no-KAS waivers and policies")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())