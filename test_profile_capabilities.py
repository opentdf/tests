#!/usr/bin/env python3
"""Test to verify profile capability checking."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from framework.core import ProfileManager


def test_capability_checking():
    """Test capability checking between profiles."""
    
    profiles_dir = Path(__file__).parent / "profiles"
    pm = ProfileManager(profiles_dir)
    
    # Load both profiles
    no_kas = pm.load_profile("no-kas")
    cross_sdk = pm.load_profile("cross-sdk-basic")
    
    print("=" * 60)
    print("Profile Capability Comparison")
    print("=" * 60)
    
    # Test scenarios with required capabilities
    test_scenarios = [
        {
            "name": "Cross-SDK Nano TDF encryption",
            "caps": {"format": "nano", "encryption": "aes256gcm"}
        },
        {
            "name": "Standard TDF3 encryption",
            "caps": {"format": "ztdf", "encryption": "aes256gcm"}
        },
        {
            "name": "ABAC policy enforcement",
            "caps": {"policy": "abac-basic"}
        },
        {
            "name": "KAS rewrap operation",
            "caps": {"kas_type": "standard"}
        },
        {
            "name": "Framework demo",
            "caps": {"framework": "core"}
        },
        {
            "name": "Service validation",
            "caps": {"operations": "validate_schema"}
        }
    ]
    
    print("\nScenario Execution by Profile:")
    print("-" * 60)
    print(f"{'Scenario':<35} {'cross-sdk-basic':<20} {'no-kas':<20}")
    print("-" * 60)
    
    for scenario in test_scenarios:
        cross_sdk_can_run = True
        no_kas_can_run = True
        
        # Check cross-sdk-basic
        for cap_key, cap_value in scenario["caps"].items():
            if cap_key not in cross_sdk.capabilities:
                cross_sdk_can_run = False
                break
            if cap_value not in cross_sdk.capabilities[cap_key]:
                cross_sdk_can_run = False
                break
        
        # Check no-kas
        for cap_key, cap_value in scenario["caps"].items():
            if cap_key not in no_kas.capabilities:
                no_kas_can_run = False
                break
            if cap_value not in no_kas.capabilities[cap_key]:
                no_kas_can_run = False
                break
        
        cross_status = "✓ RUN" if cross_sdk_can_run else "⊘ SKIP"
        no_kas_status = "✓ RUN" if no_kas_can_run else "⊘ SKIP"
        
        print(f"{scenario['name']:<35} {cross_status:<20} {no_kas_status:<20}")
    
    print("\n" + "=" * 60)
    print("Key Observations:")
    print("- no-kas profile skips ALL encryption scenarios")
    print("- no-kas profile can only run non-cryptographic tests")
    print("- cross-sdk-basic runs all encryption tests")
    print("=" * 60)


if __name__ == "__main__":
    test_capability_checking()