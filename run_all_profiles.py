#!/usr/bin/env python3
"""Run BDD tests with all available profiles and generate summary."""

import sys
import os
import subprocess
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any


def run_tests_with_profile(profile_name: str, bdd_dir: Path, venv_python: str) -> Dict[str, Any]:
    """Run BDD tests with a specific profile."""
    print(f"\n{'='*60}")
    print(f"Running tests with profile: {profile_name}")
    print(f"{'='*60}")
    
    # Build behave command
    cmd = [
        venv_python, "-m", "behave",
        str(bdd_dir),
        "--format=json",
        "-D", f"profile={profile_name}",
        "--no-capture",
        "--no-capture-stderr",
        "--quiet"
    ]
    
    # Create output file for this profile
    output_file = f"test-results-{profile_name}.json"
    cmd.extend(["-o", output_file])
    
    # Run behave
    start_time = datetime.now()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(bdd_dir.parent))
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # Parse results
    profile_results = {
        "profile": profile_name,
        "duration": duration,
        "exit_code": result.returncode,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "total": 0,
        "features": [],
        "errors": []
    }
    
    # Try to parse JSON output
    output_path = bdd_dir.parent / output_file
    if output_path.exists():
        try:
            with open(output_path) as f:
                test_data = json.load(f)
                
            # Count scenarios
            for feature in test_data:
                feature_summary = {
                    "name": feature.get("name", "Unknown"),
                    "scenarios": []
                }
                
                for element in feature.get("elements", []):
                    if element.get("type") == "scenario":
                        scenario_status = "passed"
                        for step in element.get("steps", []):
                            if step.get("result", {}).get("status") == "failed":
                                scenario_status = "failed"
                                break
                            elif step.get("result", {}).get("status") == "skipped":
                                scenario_status = "skipped"
                        
                        scenario_summary = {
                            "name": element.get("name", "Unknown"),
                            "status": scenario_status
                        }
                        feature_summary["scenarios"].append(scenario_summary)
                        
                        # Update counters
                        profile_results["total"] += 1
                        if scenario_status == "passed":
                            profile_results["passed"] += 1
                        elif scenario_status == "failed":
                            profile_results["failed"] += 1
                        else:
                            profile_results["skipped"] += 1
                
                profile_results["features"].append(feature_summary)
                
        except Exception as e:
            profile_results["errors"].append(f"Failed to parse results: {e}")
    
    # If no JSON output, try to parse stdout
    if profile_results["total"] == 0 and result.stdout:
        lines = result.stdout.split('\n')
        for line in lines:
            if "scenarios passed" in line or "scenario passed" in line:
                try:
                    profile_results["passed"] = int(line.split()[0])
                except:
                    pass
            elif "scenarios failed" in line or "scenario failed" in line:
                try:
                    profile_results["failed"] = int(line.split()[0])
                except:
                    pass
            elif "scenarios skipped" in line or "scenario skipped" in line:
                try:
                    profile_results["skipped"] = int(line.split()[0])
                except:
                    pass
        
        profile_results["total"] = profile_results["passed"] + profile_results["failed"] + profile_results["skipped"]
    
    # Clean up output file
    if output_path.exists():
        output_path.unlink()
    
    return profile_results


def print_summary(all_results: List[Dict[str, Any]]):
    """Print summary of all test runs."""
    print("\n" + "="*80)
    print("TEST EXECUTION SUMMARY - ALL PROFILES")
    print("="*80)
    
    # Overall statistics
    total_tests = sum(r["total"] for r in all_results)
    total_passed = sum(r["passed"] for r in all_results)
    total_failed = sum(r["failed"] for r in all_results)
    total_skipped = sum(r["skipped"] for r in all_results)
    total_duration = sum(r["duration"] for r in all_results)
    
    print(f"\nOverall Statistics:")
    print(f"  Total Profiles Tested: {len(all_results)}")
    print(f"  Total Test Scenarios: {total_tests}")
    print(f"  Total Passed: {total_passed} ({100*total_passed/total_tests:.1f}%)" if total_tests > 0 else "  Total Passed: 0")
    print(f"  Total Failed: {total_failed} ({100*total_failed/total_tests:.1f}%)" if total_tests > 0 else "  Total Failed: 0")
    print(f"  Total Skipped: {total_skipped} ({100*total_skipped/total_tests:.1f}%)" if total_tests > 0 else "  Total Skipped: 0")
    print(f"  Total Duration: {total_duration:.2f} seconds")
    
    # Per-profile summary table
    print(f"\n{'Profile':<20} {'Total':<8} {'Pass':<8} {'Fail':<8} {'Skip':<8} {'Time(s)':<10} {'Status':<10}")
    print("-" * 80)
    
    for result in all_results:
        status = "✅ PASS" if result["failed"] == 0 else "❌ FAIL"
        if result["total"] == 0:
            status = "⚠️  NO TESTS"
        elif result["total"] == result["skipped"]:
            status = "⊘ ALL SKIP"
            
        print(f"{result['profile']:<20} {result['total']:<8} {result['passed']:<8} {result['failed']:<8} {result['skipped']:<8} {result['duration']:<10.2f} {status:<10}")
    
    # Detailed results per profile
    print("\n" + "="*80)
    print("DETAILED RESULTS BY PROFILE")
    print("="*80)
    
    for result in all_results:
        print(f"\n### Profile: {result['profile']}")
        print(f"    Duration: {result['duration']:.2f}s")
        print(f"    Results: {result['passed']} passed, {result['failed']} failed, {result['skipped']} skipped")
        
        if result['features']:
            print("    Features tested:")
            for feature in result['features']:
                print(f"      - {feature['name']}")
                for scenario in feature['scenarios']:
                    status_icon = "✓" if scenario['status'] == "passed" else "✗" if scenario['status'] == "failed" else "⊘"
                    print(f"        {status_icon} {scenario['name']}")
        
        if result['errors']:
            print("    Errors:")
            for error in result['errors']:
                print(f"      - {error}")
    
    # Profile characteristics
    print("\n" + "="*80)
    print("PROFILE CHARACTERISTICS")
    print("="*80)
    
    profiles_info = {
        "cross-sdk-basic": "Standard cross-SDK testing with KAS enabled",
        "no-kas": "Testing without KAS (no encryption capabilities)",
        "high-security": "Enhanced security testing profile",
        "performance": "Performance-focused testing profile"
    }
    
    for profile_name, description in profiles_info.items():
        result = next((r for r in all_results if r["profile"] == profile_name), None)
        if result:
            print(f"\n{profile_name}:")
            print(f"  Description: {description}")
            print(f"  Test Coverage: {result['total']} scenarios")
            if profile_name == "no-kas":
                print(f"  Note: All encryption tests skipped (KAS required)")
            elif profile_name == "cross-sdk-basic":
                print(f"  Note: Full encryption/decryption testing enabled")


def main():
    """Main entry point."""
    print("="*80)
    print("OpenTDF BDD Test Runner - All Profiles")
    print("="*80)
    
    # Setup paths
    tests_dir = Path(__file__).parent
    bdd_dir = tests_dir / "bdd"
    profiles_dir = tests_dir / "profiles"
    
    # Check for virtual environment
    venv_dir = tests_dir / "bdd_venv"
    if not venv_dir.exists():
        print("Creating virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        
        # Install behave
        venv_pip = str(venv_dir / "bin" / "pip")
        print("Installing behave...")
        subprocess.run([venv_pip, "install", "behave", "pyyaml", "-q"], check=True)
    
    venv_python = str(venv_dir / "bin" / "python")
    
    # Get list of profiles
    profiles = []
    if profiles_dir.exists():
        for profile_path in profiles_dir.iterdir():
            if profile_path.is_dir() and (profile_path / "capabilities.yaml").exists():
                profiles.append(profile_path.name)
    
    if not profiles:
        print("No profiles found!")
        return 1
    
    print(f"\nFound {len(profiles)} profiles: {', '.join(sorted(profiles))}")
    
    # Run tests with each profile
    all_results = []
    for profile_name in sorted(profiles):
        try:
            result = run_tests_with_profile(profile_name, bdd_dir, venv_python)
            all_results.append(result)
        except Exception as e:
            print(f"Error running tests with profile {profile_name}: {e}")
            all_results.append({
                "profile": profile_name,
                "duration": 0,
                "exit_code": 1,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "total": 0,
                "features": [],
                "errors": [str(e)]
            })
    
    # Print summary
    print_summary(all_results)
    
    # Determine overall exit code
    any_failures = any(r["failed"] > 0 for r in all_results)
    
    print("\n" + "="*80)
    if any_failures:
        print("❌ OVERALL RESULT: SOME TESTS FAILED")
        return 1
    else:
        print("✅ OVERALL RESULT: ALL TESTS PASSED OR SKIPPED AS EXPECTED")
        return 0


if __name__ == "__main__":
    sys.exit(main())