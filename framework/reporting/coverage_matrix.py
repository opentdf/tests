"""Coverage matrix generator for unified test suite reporting."""

import ast
import json
import logging
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..core.profiles import ProfileManager
from .models import (
    CoverageGap,
    CoverageMatrix,
    CapabilityCoverage,
    RequirementCoverage,
    SDKMatrix,
    TestInfo,
    TestStatus,
    TestSuite,
    TestSuiteCoverage,
)

logger = logging.getLogger(__name__)


class TestDiscoverer:
    """Discovers tests from different test suites."""
    
    def discover_xtest(self, path: Path) -> List[TestInfo]:
        """Discover pytest tests from xtest directory."""
        tests = []
        test_dir = path / "xtest"
        
        if not test_dir.exists():
            logger.warning(f"XTest directory not found: {test_dir}")
            return tests
        
        # Parse Python test files
        for test_file in test_dir.glob("test_*.py"):
            try:
                with open(test_file) as f:
                    tree = ast.parse(f.read())
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                        test_info = self._extract_pytest_markers(node, test_file)
                        tests.append(test_info)
            except Exception as e:
                logger.error(f"Error parsing {test_file}: {e}")
        
        return tests
    
    def discover_bdd(self, path: Path) -> List[TestInfo]:
        """Discover BDD tests from feature files."""
        tests = []
        bdd_dir = path / "bdd" / "features"
        
        if not bdd_dir.exists():
            logger.warning(f"BDD features directory not found: {bdd_dir}")
            return tests
        
        # Parse feature files
        for feature_file in bdd_dir.glob("*.feature"):
            try:
                tests.extend(self._parse_feature_file(feature_file))
            except Exception as e:
                logger.error(f"Error parsing {feature_file}: {e}")
        
        return tests
    
    def discover_tdd(self, path: Path) -> List[TestInfo]:
        """Discover TDD tests (placeholder for future)."""
        # TODO: Implement TDD test discovery when suite is added
        return []
    
    def discover_pen(self, path: Path) -> List[TestInfo]:
        """Discover penetration tests (placeholder for future)."""
        # TODO: Implement pen test discovery when suite is added
        return []
    
    def _extract_pytest_markers(self, node: ast.FunctionDef, file_path: Path) -> TestInfo:
        """Extract markers from a pytest function."""
        test_info = TestInfo(
            suite=TestSuite.XTEST,
            file=file_path.name,
            name=node.name,
            full_name=f"xtest::{file_path.name}::{node.name}"
        )
        
        # Extract decorators
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Attribute):
                    if decorator.func.attr == "req" and decorator.args:
                        # @pytest.mark.req("BR-101")
                        if isinstance(decorator.args[0], ast.Constant):
                            test_info.requirement_ids.append(decorator.args[0].value)
                    
                    elif decorator.func.attr == "cap" and decorator.keywords:
                        # @pytest.mark.cap(sdk="go", format="nano")
                        for keyword in decorator.keywords:
                            if isinstance(keyword.value, ast.Constant):
                                test_info.capabilities[keyword.arg] = keyword.value.value
        
        return test_info
    
    def _parse_feature_file(self, feature_file: Path) -> List[TestInfo]:
        """Parse a Gherkin feature file."""
        tests = []
        current_feature = None
        current_scenario = None
        feature_tags = []
        scenario_tags = []
        
        with open(feature_file) as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            
            # Parse tags
            if line.startswith("@"):
                tags = line.split()
                if current_scenario is None:
                    feature_tags = tags
                else:
                    scenario_tags = tags
            
            # Parse feature
            elif line.startswith("Feature:"):
                current_feature = line[8:].strip()
                feature_tags = []
            
            # Parse scenario
            elif line.startswith("Scenario:") or line.startswith("Scenario Outline:"):
                if current_feature:
                    scenario_name = line.split(":", 1)[1].strip()
                    test_info = TestInfo(
                        suite=TestSuite.BDD,
                        file=feature_file.name,
                        name=scenario_name,
                        full_name=f"bdd::{feature_file.name}::{scenario_name}"
                    )
                    
                    # Parse tags from both feature and scenario
                    all_tags = feature_tags + scenario_tags
                    for tag in all_tags:
                        if tag.startswith("@req:"):
                            test_info.requirement_ids.append(tag[5:])
                        elif tag.startswith("@cap:"):
                            # Parse capability tags like @cap:format=nano
                            cap_match = re.match(r"@cap:(\w+)=(\w+)", tag)
                            if cap_match:
                                test_info.capabilities[cap_match.group(1)] = cap_match.group(2)
                        else:
                            test_info.tags.add(tag[1:] if tag.startswith("@") else tag)
                    
                    tests.append(test_info)
                    scenario_tags = []
        
        return tests


class CoverageMatrixGenerator:
    """Generates unified coverage matrix across all test suites."""
    
    def __init__(self, base_path: Path = None):
        """Initialize the generator.
        
        Args:
            base_path: Base path for test suites (defaults to current directory)
        """
        self.base_path = base_path or Path.cwd()
        self.discoverer = TestDiscoverer()
        self.profile_manager = None
        
        # Try to load profile manager
        profiles_dir = self.base_path / "profiles"
        if profiles_dir.exists():
            self.profile_manager = ProfileManager(profiles_dir)
    
    def generate(
        self,
        profile_id: Optional[str] = None,
        evidence_dir: Optional[Path] = None,
        include_suites: Optional[List[TestSuite]] = None
    ) -> CoverageMatrix:
        """Generate coverage matrix.
        
        Args:
            profile_id: Profile to use for capability analysis
            evidence_dir: Directory containing test execution evidence
            include_suites: List of test suites to include (defaults to all)
        
        Returns:
            Complete coverage matrix
        """
        matrix = CoverageMatrix(
            profile_id=profile_id,
            evidence_dir=evidence_dir
        )
        
        # Determine which suites to analyze
        if include_suites is None:
            include_suites = [TestSuite.XTEST, TestSuite.BDD, TestSuite.TDD, TestSuite.PEN]
        
        # Discover tests from each suite
        all_tests = []
        for suite in include_suites:
            suite_tests = self._discover_suite(suite)
            if suite_tests:
                # Create suite coverage
                suite_coverage = TestSuiteCoverage(
                    suite=suite,
                    path=self._get_suite_path(suite),
                    total_tests=len(suite_tests)
                )
                
                # Organize tests by file
                for test in suite_tests:
                    if test.file not in suite_coverage.files:
                        suite_coverage.files.append(test.file)
                        suite_coverage.tests_by_file[test.file] = []
                    suite_coverage.tests_by_file[test.file].append(test.name)
                    
                    # Track requirements
                    for req_id in test.requirement_ids:
                        suite_coverage.requirements_covered.add(req_id)
                        if req_id not in suite_coverage.tests_by_requirement:
                            suite_coverage.tests_by_requirement[req_id] = []
                        suite_coverage.tests_by_requirement[req_id].append(test.name)
                    
                    # Track capabilities
                    for cap_key, cap_value in test.capabilities.items():
                        if cap_key not in suite_coverage.capabilities_covered:
                            suite_coverage.capabilities_covered[cap_key] = set()
                        suite_coverage.capabilities_covered[cap_key].add(cap_value)
                
                matrix.test_suites[suite] = suite_coverage
                all_tests.extend(suite_tests)
        
        # Load test results from evidence if provided
        if evidence_dir and evidence_dir.exists():
            self._load_evidence(all_tests, evidence_dir)
        
        # Add all tests to matrix
        for test in all_tests:
            matrix.add_test(test)
        
        # Build SDK matrix for xtest
        if TestSuite.XTEST in include_suites:
            matrix.sdk_matrix = self._build_sdk_matrix(
                [t for t in all_tests if t.suite == TestSuite.XTEST]
            )
        
        # Identify coverage gaps
        if profile_id and self.profile_manager:
            try:
                profile = self.profile_manager.load_profile(profile_id)
                matrix.gaps = self._identify_gaps(matrix, profile)
            except Exception as e:
                logger.error(f"Could not load profile {profile_id}: {e}")
        
        # Calculate summary statistics
        matrix.calculate_summary()
        
        return matrix
    
    def _discover_suite(self, suite: TestSuite) -> List[TestInfo]:
        """Discover tests from a specific suite."""
        if suite == TestSuite.XTEST:
            return self.discoverer.discover_xtest(self.base_path)
        elif suite == TestSuite.BDD:
            return self.discoverer.discover_bdd(self.base_path)
        elif suite == TestSuite.TDD:
            return self.discoverer.discover_tdd(self.base_path)
        elif suite == TestSuite.PEN:
            return self.discoverer.discover_pen(self.base_path)
        else:
            logger.warning(f"Unknown test suite: {suite}")
            return []
    
    def _get_suite_path(self, suite: TestSuite) -> Path:
        """Get the path for a test suite."""
        suite_paths = {
            TestSuite.XTEST: self.base_path / "xtest",
            TestSuite.BDD: self.base_path / "bdd",
            TestSuite.TDD: self.base_path / "tdd",
            TestSuite.PEN: self.base_path / "pen",
        }
        return suite_paths.get(suite, self.base_path / suite.value)
    
    def _load_evidence(self, tests: List[TestInfo], evidence_dir: Path) -> None:
        """Load test execution results from evidence files."""
        # Map test names to test info objects
        test_map = {test.full_name: test for test in tests}
        
        # Load evidence JSON files
        for evidence_file in evidence_dir.rglob("*_evidence.json"):
            try:
                with open(evidence_file) as f:
                    evidence = json.load(f)
                
                # Match evidence to test
                test_name = evidence.get("test_name", "")
                if test_name in test_map:
                    test = test_map[test_name]
                    
                    # Update test status
                    outcome = evidence.get("outcome", "").lower()
                    if outcome == "passed":
                        test.status = TestStatus.PASSED
                    elif outcome == "failed":
                        test.status = TestStatus.FAILED
                    elif outcome == "skipped":
                        test.status = TestStatus.SKIPPED
                    else:
                        test.status = TestStatus.ERROR
                    
                    # Update duration
                    test.duration = evidence.get("duration")
                    
            except Exception as e:
                logger.error(f"Error loading evidence from {evidence_file}: {e}")
    
    def _build_sdk_matrix(self, xtest_tests: List[TestInfo]) -> SDKMatrix:
        """Build SDK compatibility matrix from xtest tests."""
        matrix = SDKMatrix()
        
        # Analyze tests that have SDK capabilities
        for test in xtest_tests:
            sdk_cap = test.capabilities.get("sdk", "")
            
            # Handle parametrized SDK tests (encrypt x decrypt combinations)
            if sdk_cap == "parametrized":
                # These tests cover all SDK combinations
                # We need to look at the test name or other markers
                # to determine actual SDK coverage
                # For now, assume it covers all combinations
                sdks = ["go", "java", "js", "swift"]
                for from_sdk in sdks:
                    if from_sdk not in matrix.combinations:
                        matrix.combinations[from_sdk] = {}
                        matrix.results[from_sdk] = {}
                    for to_sdk in sdks:
                        if to_sdk not in matrix.combinations[from_sdk]:
                            matrix.combinations[from_sdk][to_sdk] = 0
                            matrix.results[from_sdk][to_sdk] = {
                                "passed": 0, "failed": 0, "skipped": 0
                            }
                        matrix.combinations[from_sdk][to_sdk] += 1
                        
                        # Update results based on test status
                        if test.status == TestStatus.PASSED:
                            matrix.results[from_sdk][to_sdk]["passed"] += 1
                        elif test.status == TestStatus.FAILED:
                            matrix.results[from_sdk][to_sdk]["failed"] += 1
                        elif test.status == TestStatus.SKIPPED:
                            matrix.results[from_sdk][to_sdk]["skipped"] += 1
            
            elif sdk_cap:
                # Single SDK test
                if sdk_cap not in matrix.combinations:
                    matrix.combinations[sdk_cap] = {}
                    matrix.results[sdk_cap] = {}
        
        return matrix
    
    def _identify_gaps(self, matrix: CoverageMatrix, profile: Any) -> List[CoverageGap]:
        """Identify coverage gaps based on profile capabilities."""
        gaps = []
        
        # Check requirement coverage
        expected_requirements = ["BR-101", "BR-102", "BR-301", "BR-302", "BR-303"]
        for req_id in expected_requirements:
            if req_id not in matrix.requirements:
                gaps.append(CoverageGap(
                    gap_type="missing_requirement",
                    severity="high",
                    description=f"No tests found for requirement {req_id}",
                    requirement_id=req_id
                ))
            elif matrix.requirements[req_id].total_tests < 3:
                gaps.append(CoverageGap(
                    gap_type="insufficient_requirement_coverage",
                    severity="medium",
                    description=f"Only {matrix.requirements[req_id].total_tests} tests for {req_id}",
                    requirement_id=req_id
                ))
        
        # Check capability coverage against profile
        if hasattr(profile, 'capabilities'):
            for cap_key, cap_values in profile.capabilities.items():
                if cap_key not in matrix.capabilities:
                    gaps.append(CoverageGap(
                        gap_type="missing_capability_dimension",
                        severity="high",
                        description=f"No tests found for capability dimension '{cap_key}'",
                        capability={cap_key: "any"}
                    ))
                else:
                    for cap_value in cap_values:
                        if cap_value not in matrix.capabilities[cap_key]:
                            gaps.append(CoverageGap(
                                gap_type="missing_capability",
                                severity="medium",
                                description=f"No tests for {cap_key}={cap_value}",
                                capability={cap_key: cap_value}
                            ))
        
        # Check SDK combinations for xtest
        if matrix.sdk_matrix and hasattr(profile, 'capabilities') and 'sdk' in profile.capabilities:
            sdks = profile.capabilities['sdk']
            for from_sdk in sdks:
                for to_sdk in sdks:
                    if from_sdk != to_sdk:
                        coverage = matrix.sdk_matrix.get_coverage(from_sdk, to_sdk)
                        if coverage == 0:
                            gaps.append(CoverageGap(
                                gap_type="missing_sdk_combination",
                                severity="high" if from_sdk in ["go", "java"] else "medium",
                                description=f"No cross-SDK tests for {from_sdk} -> {to_sdk}",
                                sdk_combination=(from_sdk, to_sdk),
                                test_suite=TestSuite.XTEST
                            ))
        
        # Check for suites with no tests
        for suite in [TestSuite.XTEST, TestSuite.BDD]:
            if suite not in matrix.test_suites or matrix.test_suites[suite].total_tests == 0:
                gaps.append(CoverageGap(
                    gap_type="empty_test_suite",
                    severity="high",
                    description=f"Test suite '{suite.value}' has no tests",
                    test_suite=suite
                ))
        
        return gaps