"""Pydantic models for coverage reporting."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field, ConfigDict


class TestSuite(str, Enum):
    """Supported test suite types."""
    XTEST = "xtest"
    BDD = "bdd"
    TDD = "tdd"  # Future: Test-driven development suite
    PEN = "pen"  # Future: Penetration testing suite
    PERF = "perf"  # Future: Performance testing suite
    VULN = "vuln"  # Future: Vulnerability testing suite


class TestStatus(str, Enum):
    """Test execution status."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    PENDING = "pending"
    NOT_RUN = "not_run"


class TestInfo(BaseModel):
    """Information about a single test."""
    
    model_config = ConfigDict(extra="forbid")
    
    suite: TestSuite
    file: str
    name: str
    full_name: str  # suite::file::name
    requirement_ids: List[str] = Field(default_factory=list)
    capabilities: Dict[str, str] = Field(default_factory=dict)
    tags: Set[str] = Field(default_factory=set)
    status: TestStatus = Field(default=TestStatus.NOT_RUN)
    duration: Optional[float] = None
    error_message: Optional[str] = None


class RequirementCoverage(BaseModel):
    """Coverage information for a business requirement."""
    
    model_config = ConfigDict(extra="forbid")
    
    requirement_id: str
    description: Optional[str] = None
    priority: str = Field(default="P1")
    
    # Test coverage by suite
    test_suites: Dict[TestSuite, List[str]] = Field(default_factory=dict)  # suite -> test names
    total_tests: int = Field(default=0)
    
    # Execution results
    passed: int = Field(default=0)
    failed: int = Field(default=0)
    skipped: int = Field(default=0)
    not_run: int = Field(default=0)
    
    @property
    def coverage_percent(self) -> float:
        """Calculate coverage percentage."""
        if self.total_tests == 0:
            return 0.0
        executed = self.passed + self.failed
        return (executed / self.total_tests) * 100
    
    @property
    def pass_rate(self) -> float:
        """Calculate pass rate for executed tests."""
        executed = self.passed + self.failed
        if executed == 0:
            return 0.0
        return (self.passed / executed) * 100


class CapabilityCoverage(BaseModel):
    """Coverage for a specific capability dimension."""
    
    model_config = ConfigDict(extra="forbid")
    
    capability_key: str  # e.g., "sdk", "format", "feature"
    capability_value: str  # e.g., "go", "nano", "assertions"
    
    # Tests covering this capability
    test_suites: Dict[TestSuite, List[str]] = Field(default_factory=dict)
    total_tests: int = Field(default=0)
    
    # Cross-product coverage (for multi-valued capabilities)
    combinations: Dict[str, int] = Field(default_factory=dict)  # e.g., "go->java": 5
    
    # Execution results
    passed: int = Field(default=0)
    failed: int = Field(default=0)
    skipped: int = Field(default=0)


class TestSuiteCoverage(BaseModel):
    """Coverage information for a test suite."""
    
    model_config = ConfigDict(extra="forbid")
    
    suite: TestSuite
    path: Path
    total_tests: int = Field(default=0)
    
    # Test organization
    files: List[str] = Field(default_factory=list)
    tests_by_file: Dict[str, List[str]] = Field(default_factory=dict)
    
    # Requirement coverage
    requirements_covered: Set[str] = Field(default_factory=set)
    tests_by_requirement: Dict[str, List[str]] = Field(default_factory=dict)
    
    # Capability coverage
    capabilities_covered: Dict[str, Set[str]] = Field(default_factory=dict)
    
    # Execution status
    passed: int = Field(default=0)
    failed: int = Field(default=0)
    skipped: int = Field(default=0)
    error: int = Field(default=0)
    not_run: int = Field(default=0)
    
    @property
    def execution_rate(self) -> float:
        """Percentage of tests that were executed."""
        if self.total_tests == 0:
            return 0.0
        executed = self.passed + self.failed + self.error
        return (executed / self.total_tests) * 100
    
    @property
    def pass_rate(self) -> float:
        """Pass rate for executed tests."""
        executed = self.passed + self.failed + self.error
        if executed == 0:
            return 0.0
        return (self.passed / executed) * 100


class SDKMatrix(BaseModel):
    """SDK compatibility matrix."""
    
    model_config = ConfigDict(extra="forbid")
    
    # Matrix of SDK combinations
    combinations: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    # e.g., {"go": {"java": 15, "js": 12}, "java": {"go": 15, "js": 10}}
    
    # Results for each combination
    results: Dict[str, Dict[str, Dict[str, int]]] = Field(default_factory=dict)
    # e.g., {"go": {"java": {"passed": 14, "failed": 1}}}
    
    def get_coverage(self, from_sdk: str, to_sdk: str) -> Optional[int]:
        """Get test count for SDK combination."""
        return self.combinations.get(from_sdk, {}).get(to_sdk, 0)


class CoverageGap(BaseModel):
    """Identified gap in test coverage."""
    
    model_config = ConfigDict(extra="forbid")
    
    gap_type: str  # "missing_requirement", "missing_capability", "missing_combination"
    severity: str = Field(default="medium")  # high, medium, low
    description: str
    
    # Specific gap details
    requirement_id: Optional[str] = None
    capability: Optional[Dict[str, str]] = None
    sdk_combination: Optional[tuple[str, str]] = None
    test_suite: Optional[TestSuite] = None
    
    # Suggested action
    suggested_tests: List[str] = Field(default_factory=list)
    estimated_effort: Optional[str] = None  # e.g., "2 hours", "1 day"


class CoverageMatrix(BaseModel):
    """Complete coverage matrix across all test suites."""
    
    model_config = ConfigDict(extra="allow")
    
    # Metadata
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    profile_id: Optional[str] = None
    evidence_dir: Optional[Path] = None
    
    # Test suites analyzed
    test_suites: Dict[TestSuite, TestSuiteCoverage] = Field(default_factory=dict)
    
    # All discovered tests
    all_tests: List[TestInfo] = Field(default_factory=list)
    total_tests: int = Field(default=0)
    
    # Requirement coverage across all suites
    requirements: Dict[str, RequirementCoverage] = Field(default_factory=dict)
    
    # Capability coverage across all suites
    capabilities: Dict[str, Dict[str, CapabilityCoverage]] = Field(default_factory=dict)
    # e.g., {"sdk": {"go": CapabilityCoverage, "java": CapabilityCoverage}}
    
    # SDK compatibility matrix (for xtest primarily)
    sdk_matrix: Optional[SDKMatrix] = None
    
    # Coverage gaps
    gaps: List[CoverageGap] = Field(default_factory=list)
    
    # Summary statistics
    summary: Dict[str, Any] = Field(default_factory=dict)
    
    def add_test(self, test: TestInfo) -> None:
        """Add a test to the coverage matrix."""
        self.all_tests.append(test)
        self.total_tests += 1
        
        # Update requirement coverage
        for req_id in test.requirement_ids:
            if req_id not in self.requirements:
                self.requirements[req_id] = RequirementCoverage(requirement_id=req_id)
            
            req_cov = self.requirements[req_id]
            if test.suite not in req_cov.test_suites:
                req_cov.test_suites[test.suite] = []
            req_cov.test_suites[test.suite].append(test.full_name)
            req_cov.total_tests += 1
            
            # Update status counts
            if test.status == TestStatus.PASSED:
                req_cov.passed += 1
            elif test.status == TestStatus.FAILED:
                req_cov.failed += 1
            elif test.status == TestStatus.SKIPPED:
                req_cov.skipped += 1
            else:
                req_cov.not_run += 1
        
        # Update capability coverage
        for cap_key, cap_value in test.capabilities.items():
            if cap_key not in self.capabilities:
                self.capabilities[cap_key] = {}
            if cap_value not in self.capabilities[cap_key]:
                self.capabilities[cap_key][cap_value] = CapabilityCoverage(
                    capability_key=cap_key,
                    capability_value=cap_value
                )
            
            cap_cov = self.capabilities[cap_key][cap_value]
            if test.suite not in cap_cov.test_suites:
                cap_cov.test_suites[test.suite] = []
            cap_cov.test_suites[test.suite].append(test.full_name)
            cap_cov.total_tests += 1
            
            # Update status counts
            if test.status == TestStatus.PASSED:
                cap_cov.passed += 1
            elif test.status == TestStatus.FAILED:
                cap_cov.failed += 1
            elif test.status == TestStatus.SKIPPED:
                cap_cov.skipped += 1
    
    def calculate_summary(self) -> None:
        """Calculate summary statistics."""
        self.summary = {
            "total_tests": self.total_tests,
            "total_suites": len(self.test_suites),
            "requirements_covered": len(self.requirements),
            "total_gaps": len(self.gaps),
            "high_severity_gaps": len([g for g in self.gaps if g.severity == "high"]),
            
            # Overall execution stats
            "total_passed": sum(r.passed for r in self.requirements.values()),
            "total_failed": sum(r.failed for r in self.requirements.values()),
            "total_skipped": sum(r.skipped for r in self.requirements.values()),
            "total_not_run": sum(r.not_run for r in self.requirements.values()),
            
            # Coverage percentages
            "requirement_coverage": {
                req_id: req.coverage_percent 
                for req_id, req in self.requirements.items()
            },
            
            # Per-suite summary
            "suite_summary": {
                suite.value: {
                    "total": cov.total_tests,
                    "passed": cov.passed,
                    "failed": cov.failed,
                    "pass_rate": cov.pass_rate
                }
                for suite, cov in self.test_suites.items()
            }
        }
    
    def to_json_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        data = self.model_dump(exclude_none=True)
        
        # Convert Path objects to strings
        if "evidence_dir" in data and data["evidence_dir"]:
            data["evidence_dir"] = str(data["evidence_dir"])
        
        # Convert datetime to ISO format
        if "generated_at" in data:
            data["generated_at"] = data["generated_at"].isoformat()
        
        # Convert enums to strings
        for suite in data.get("test_suites", {}).values():
            if "path" in suite:
                suite["path"] = str(suite["path"])
        
        return data