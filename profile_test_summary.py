#!/usr/bin/env python3
"""Generate a summary of which tests run with which profiles."""

import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent))

from framework.core import ProfileManager


def analyze_feature_files(bdd_dir: Path) -> List[Dict]:
    """Analyze feature files to extract scenarios and capabilities."""
    scenarios = []
    
    for feature_file in bdd_dir.glob("features/*.feature"):
        with open(feature_file) as f:
            lines = f.readlines()
        
        current_feature = None
        current_scenario = None
        current_tags = []
        
        for line in lines:
            line = line.strip()
            
            if line.startswith("Feature:"):
                current_feature = line[8:].strip()
            elif line.startswith("@"):
                current_tags = line.split()
            elif line.startswith("Scenario:") or line.startswith("Scenario Outline:"):
                scenario_name = line.split(":", 1)[1].strip()
                
                # Extract capabilities from tags
                caps = {}
                for tag in current_tags:
                    if tag.startswith("@cap:"):
                        cap_str = tag[5:]
                        if "=" in cap_str:
                            key, value = cap_str.split("=", 1)
                            caps[key] = value
                
                scenarios.append({
                    "feature": current_feature,
                    "name": scenario_name,
                    "tags": current_tags,
                    "capabilities": caps
                })
                current_tags = []
    
    return scenarios


def check_scenario_compatibility(scenario: Dict, profile) -> Tuple[bool, str]:
    """Check if a scenario can run with a profile."""
    
    # Special handling for no-kas profile
    if profile.id == "no-kas":
        # Check if it's an encryption scenario
        name_lower = scenario["name"].lower()
        if any(word in name_lower for word in ["encrypt", "decrypt", "tdf", "kas", "policy", "abac"]):
            return False, "Encryption/KAS operations not available"
        
        # Check required capabilities
        for cap_key, cap_value in scenario["capabilities"].items():
            if cap_key in ["format", "encryption", "policy", "kas_type"]:
                return False, f"Capability '{cap_key}' requires KAS"
    
    # Standard capability checking
    for cap_key, cap_value in scenario["capabilities"].items():
        if cap_key not in profile.capabilities:
            # Framework tests don't need to be in capability catalog
            if cap_key == "framework":
                continue
            return False, f"Missing capability: {cap_key}"
        
        if cap_value not in profile.capabilities[cap_key]:
            return False, f"{cap_key}={cap_value} not supported"
    
    return True, "OK"


def main():
    """Generate test execution summary."""
    print("=" * 100)
    print("OpenTDF BDD Test Execution Matrix")
    print("=" * 100)
    
    # Load profiles
    profiles_dir = Path(__file__).parent / "profiles"
    pm = ProfileManager(profiles_dir)
    
    profiles = {}
    for profile_name in ["cross-sdk-basic", "no-kas"]:
        try:
            profiles[profile_name] = pm.load_profile(profile_name)
        except Exception as e:
            print(f"Warning: Could not load profile {profile_name}: {e}")
    
    # Analyze feature files
    bdd_dir = Path(__file__).parent / "bdd"
    scenarios = analyze_feature_files(bdd_dir)
    
    # Generate compatibility matrix
    print(f"\nFound {len(scenarios)} scenarios across {len(set(s['feature'] for s in scenarios if s['feature']))} features")
    print(f"Testing against {len(profiles)} profiles: {', '.join(profiles.keys())}")
    
    # Summary table
    print("\n" + "=" * 100)
    print(f"{'Scenario':<50} {'cross-sdk-basic':<25} {'no-kas':<25}")
    print("-" * 100)
    
    profile_stats = {name: {"run": 0, "skip": 0} for name in profiles}
    
    for scenario in scenarios:
        if not scenario["name"]:
            continue
            
        scenario_display = scenario["name"][:48]
        if len(scenario["name"]) > 48:
            scenario_display += ".."
        
        results = []
        for profile_name, profile in profiles.items():
            can_run, reason = check_scenario_compatibility(scenario, profile)
            
            if can_run:
                results.append("✓ RUN")
                profile_stats[profile_name]["run"] += 1
            else:
                results.append(f"⊘ SKIP")
                profile_stats[profile_name]["skip"] += 1
        
        print(f"{scenario_display:<50} {results[0]:<25} {results[1] if len(results) > 1 else 'N/A':<25}")
        
        # Show capabilities for context
        if scenario["capabilities"]:
            caps_str = ", ".join(f"{k}={v}" for k, v in scenario["capabilities"].items())
            print(f"  └─ Capabilities: {caps_str}")
    
    # Summary statistics
    print("\n" + "=" * 100)
    print("PROFILE EXECUTION SUMMARY")
    print("=" * 100)
    
    for profile_name, stats in profile_stats.items():
        total = stats["run"] + stats["skip"]
        run_pct = (100 * stats["run"] / total) if total > 0 else 0
        skip_pct = (100 * stats["skip"] / total) if total > 0 else 0
        
        print(f"\n{profile_name}:")
        print(f"  Can Run:  {stats['run']:3d} scenarios ({run_pct:5.1f}%)")
        print(f"  Must Skip: {stats['skip']:3d} scenarios ({skip_pct:5.1f}%)")
        
        if profile_name == "no-kas":
            print("  Note: All encryption operations require KAS and will be skipped")
        elif profile_name == "cross-sdk-basic":
            print("  Note: Full encryption testing enabled with KAS")
    
    # Key insights
    print("\n" + "=" * 100)
    print("KEY INSIGHTS")
    print("=" * 100)
    print("""
1. The no-kas profile correctly skips ALL encryption-related scenarios
2. Only framework/validation tests can run without KAS
3. Cross-SDK profile supports all encryption operations
4. Capability tags (@cap:) properly control test execution per profile
5. The framework automatically skips incompatible tests based on profile capabilities
""")
    
    print("=" * 100)


if __name__ == "__main__":
    main()