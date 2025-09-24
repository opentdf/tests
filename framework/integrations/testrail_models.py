"""TestRail data models for BDD and test management."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Any, Dict, List, Optional


class TestStatus(IntEnum):
    """TestRail test status codes."""
    PASSED = 1
    BLOCKED = 2
    UNTESTED = 3
    RETEST = 4
    FAILED = 5
    CUSTOM_STATUS_1 = 6
    CUSTOM_STATUS_2 = 7
    SKIPPED = 8
    
    @classmethod
    def from_string(cls, status: str) -> "TestStatus":
        """Convert string status to TestStatus."""
        status_map = {
            "passed": cls.PASSED,
            "pass": cls.PASSED,
            "failed": cls.FAILED,
            "fail": cls.FAILED,
            "blocked": cls.BLOCKED,
            "untested": cls.UNTESTED,
            "retest": cls.RETEST,
            "skipped": cls.SKIPPED,
            "skip": cls.SKIPPED
        }
        return status_map.get(status.lower(), cls.UNTESTED)


class TestType(IntEnum):
    """TestRail test case types."""
    ACCEPTANCE = 1
    ACCESSIBILITY = 2
    AUTOMATED = 3
    COMPATIBILITY = 4
    DESTRUCTIVE = 5
    FUNCTIONAL = 6
    OTHER = 7
    PERFORMANCE = 8
    REGRESSION = 9
    SECURITY = 10
    SMOKE_SANITY = 11
    SYSTEM = 12
    USABILITY = 13
    BDD = 14  # Custom type for BDD tests


class TestPriority(IntEnum):
    """TestRail test priority levels."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class TestCase:
    """TestRail test case model."""
    
    id: Optional[int] = None
    title: str = ""
    section_id: Optional[int] = None
    type_id: int = TestType.AUTOMATED
    priority_id: int = TestPriority.MEDIUM
    estimate: Optional[str] = None
    milestone_id: Optional[int] = None
    refs: Optional[str] = None
    
    # BDD-specific fields
    custom_gherkin: Optional[str] = None
    custom_scenario_type: Optional[str] = None  # scenario, scenario_outline, background
    custom_feature_file: Optional[str] = None
    custom_tags: Optional[List[str]] = None
    
    # Custom fields
    custom_requirements: Optional[List[str]] = None
    custom_capabilities: Optional[Dict[str, str]] = None
    custom_profile: Optional[str] = None
    custom_automation_id: Optional[str] = None
    
    # Metadata
    created_by: Optional[int] = None
    created_on: Optional[datetime] = None
    updated_by: Optional[int] = None
    updated_on: Optional[datetime] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestCase":
        """Create TestCase from dictionary."""
        return cls(
            id=data.get("id"),
            title=data.get("title", ""),
            section_id=data.get("section_id"),
            type_id=data.get("type_id", TestType.AUTOMATED),
            priority_id=data.get("priority_id", TestPriority.MEDIUM),
            estimate=data.get("estimate"),
            milestone_id=data.get("milestone_id"),
            refs=data.get("refs"),
            custom_gherkin=data.get("custom_gherkin"),
            custom_scenario_type=data.get("custom_scenario_type"),
            custom_feature_file=data.get("custom_feature_file"),
            custom_tags=data.get("custom_tags"),
            custom_requirements=data.get("custom_requirements"),
            custom_capabilities=data.get("custom_capabilities"),
            custom_profile=data.get("custom_profile"),
            custom_automation_id=data.get("custom_automation_id"),
            created_by=data.get("created_by"),
            created_on=datetime.fromtimestamp(data["created_on"]) if data.get("created_on") else None,
            updated_by=data.get("updated_by"),
            updated_on=datetime.fromtimestamp(data["updated_on"]) if data.get("updated_on") else None
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert TestCase to dictionary for API."""
        data = {
            "title": self.title,
            "type_id": self.type_id,
            "priority_id": self.priority_id
        }
        
        if self.section_id:
            data["section_id"] = self.section_id
        if self.estimate:
            data["estimate"] = self.estimate
        if self.milestone_id:
            data["milestone_id"] = self.milestone_id
        if self.refs:
            data["refs"] = self.refs
        
        # Add custom fields
        if self.custom_gherkin:
            data["custom_gherkin"] = self.custom_gherkin
        if self.custom_scenario_type:
            data["custom_scenario_type"] = self.custom_scenario_type
        if self.custom_feature_file:
            data["custom_feature_file"] = self.custom_feature_file
        if self.custom_tags:
            data["custom_tags"] = ",".join(self.custom_tags)
        if self.custom_requirements:
            data["custom_requirements"] = ",".join(self.custom_requirements)
        if self.custom_capabilities:
            data["custom_capabilities"] = str(self.custom_capabilities)
        if self.custom_profile:
            data["custom_profile"] = self.custom_profile
        if self.custom_automation_id:
            data["custom_automation_id"] = self.custom_automation_id
        
        return data


@dataclass
class TestRun:
    """TestRail test run model."""
    
    id: Optional[int] = None
    name: str = ""
    description: Optional[str] = None
    milestone_id: Optional[int] = None
    assignedto_id: Optional[int] = None
    include_all: bool = False
    is_completed: bool = False
    completed_on: Optional[datetime] = None
    config: Optional[str] = None
    config_ids: Optional[List[int]] = None
    passed_count: int = 0
    blocked_count: int = 0
    untested_count: int = 0
    retest_count: int = 0
    failed_count: int = 0
    custom_status1_count: int = 0
    custom_status2_count: int = 0
    project_id: Optional[int] = None
    plan_id: Optional[int] = None
    created_on: Optional[datetime] = None
    created_by: Optional[int] = None
    refs: Optional[str] = None
    updated_on: Optional[datetime] = None
    suite_id: Optional[int] = None
    custom_profile: Optional[str] = None
    custom_commit_sha: Optional[str] = None
    custom_run_type: Optional[str] = None  # CI, nightly, manual, etc.
    case_ids: Optional[List[int]] = None
    url: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestRun":
        """Create TestRun from dictionary."""
        return cls(
            id=data.get("id"),
            name=data.get("name", ""),
            description=data.get("description"),
            milestone_id=data.get("milestone_id"),
            assignedto_id=data.get("assignedto_id"),
            include_all=data.get("include_all", False),
            is_completed=data.get("is_completed", False),
            completed_on=datetime.fromtimestamp(data["completed_on"]) if data.get("completed_on") else None,
            config=data.get("config"),
            config_ids=data.get("config_ids"),
            passed_count=data.get("passed_count", 0),
            blocked_count=data.get("blocked_count", 0),
            untested_count=data.get("untested_count", 0),
            retest_count=data.get("retest_count", 0),
            failed_count=data.get("failed_count", 0),
            custom_status1_count=data.get("custom_status1_count", 0),
            custom_status2_count=data.get("custom_status2_count", 0),
            project_id=data.get("project_id"),
            plan_id=data.get("plan_id"),
            created_on=datetime.fromtimestamp(data["created_on"]) if data.get("created_on") else None,
            created_by=data.get("created_by"),
            refs=data.get("refs"),
            updated_on=datetime.fromtimestamp(data["updated_on"]) if data.get("updated_on") else None,
            suite_id=data.get("suite_id"),
            custom_profile=data.get("custom_profile"),
            custom_commit_sha=data.get("custom_commit_sha"),
            custom_run_type=data.get("custom_run_type"),
            case_ids=data.get("case_ids"),
            url=data.get("url")
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert TestRun to dictionary for API."""
        data = {
            "name": self.name,
            "include_all": self.include_all
        }
        
        if self.description:
            data["description"] = self.description
        if self.milestone_id:
            data["milestone_id"] = self.milestone_id
        if self.assignedto_id:
            data["assignedto_id"] = self.assignedto_id
        if self.suite_id:
            data["suite_id"] = self.suite_id
        if self.case_ids:
            data["case_ids"] = self.case_ids
        if self.refs:
            data["refs"] = self.refs
        if self.custom_profile:
            data["custom_profile"] = self.custom_profile
        if self.custom_commit_sha:
            data["custom_commit_sha"] = self.custom_commit_sha
        if self.custom_run_type:
            data["custom_run_type"] = self.custom_run_type
        
        return data


@dataclass
class TestResult:
    """TestRail test result model."""
    
    id: Optional[int] = None
    test_id: Optional[int] = None
    case_id: Optional[int] = None
    status_id: int = TestStatus.UNTESTED
    comment: Optional[str] = None
    version: Optional[str] = None
    elapsed: Optional[str] = None
    defects: Optional[str] = None
    assignedto_id: Optional[int] = None
    
    # Custom fields
    custom_artifact_url: Optional[str] = None
    custom_commit_sha: Optional[str] = None
    custom_profile: Optional[str] = None
    custom_variant: Optional[str] = None
    custom_capabilities: Optional[Dict[str, str]] = None
    custom_error_message: Optional[str] = None
    custom_stack_trace: Optional[str] = None
    custom_logs_url: Optional[str] = None
    custom_screenshots: Optional[List[str]] = None
    
    # Metadata
    created_on: Optional[datetime] = None
    created_by: Optional[int] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestResult":
        """Create TestResult from dictionary."""
        return cls(
            id=data.get("id"),
            test_id=data.get("test_id"),
            case_id=data.get("case_id"),
            status_id=data.get("status_id", TestStatus.UNTESTED),
            comment=data.get("comment"),
            version=data.get("version"),
            elapsed=data.get("elapsed"),
            defects=data.get("defects"),
            assignedto_id=data.get("assignedto_id"),
            custom_artifact_url=data.get("custom_artifact_url"),
            custom_commit_sha=data.get("custom_commit_sha"),
            custom_profile=data.get("custom_profile"),
            custom_variant=data.get("custom_variant"),
            custom_capabilities=data.get("custom_capabilities"),
            custom_error_message=data.get("custom_error_message"),
            custom_stack_trace=data.get("custom_stack_trace"),
            custom_logs_url=data.get("custom_logs_url"),
            custom_screenshots=data.get("custom_screenshots"),
            created_on=datetime.fromtimestamp(data["created_on"]) if data.get("created_on") else None,
            created_by=data.get("created_by")
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert TestResult to dictionary for API."""
        data = {
            "status_id": self.status_id
        }
        
        if self.case_id:
            data["case_id"] = self.case_id
        if self.comment:
            data["comment"] = self.comment
        if self.version:
            data["version"] = self.version
        if self.elapsed:
            data["elapsed"] = self.elapsed
        if self.defects:
            data["defects"] = self.defects
        if self.assignedto_id:
            data["assignedto_id"] = self.assignedto_id
        
        # Add custom fields
        if self.custom_artifact_url:
            data["custom_artifact_url"] = self.custom_artifact_url
        if self.custom_commit_sha:
            data["custom_commit_sha"] = self.custom_commit_sha
        if self.custom_profile:
            data["custom_profile"] = self.custom_profile
        if self.custom_variant:
            data["custom_variant"] = self.custom_variant
        if self.custom_capabilities:
            data["custom_capabilities"] = str(self.custom_capabilities)
        if self.custom_error_message:
            data["custom_error_message"] = self.custom_error_message
        if self.custom_stack_trace:
            data["custom_stack_trace"] = self.custom_stack_trace
        if self.custom_logs_url:
            data["custom_logs_url"] = self.custom_logs_url
        if self.custom_screenshots:
            data["custom_screenshots"] = ",".join(self.custom_screenshots)
        
        return data


@dataclass
class TestSection:
    """TestRail test section model."""
    
    id: Optional[int] = None
    name: str = ""
    description: Optional[str] = None
    parent_id: Optional[int] = None
    display_order: int = 0
    suite_id: Optional[int] = None
    depth: int = 0
    
    # BDD-specific fields
    custom_feature_file: Optional[str] = None
    custom_feature_description: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestSection":
        """Create TestSection from dictionary."""
        return cls(
            id=data.get("id"),
            name=data.get("name", ""),
            description=data.get("description"),
            parent_id=data.get("parent_id"),
            display_order=data.get("display_order", 0),
            suite_id=data.get("suite_id"),
            depth=data.get("depth", 0),
            custom_feature_file=data.get("custom_feature_file"),
            custom_feature_description=data.get("custom_feature_description")
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert TestSection to dictionary for API."""
        data = {
            "name": self.name
        }
        
        if self.description:
            data["description"] = self.description
        if self.parent_id:
            data["parent_id"] = self.parent_id
        if self.suite_id:
            data["suite_id"] = self.suite_id
        if self.custom_feature_file:
            data["custom_feature_file"] = self.custom_feature_file
        if self.custom_feature_description:
            data["custom_feature_description"] = self.custom_feature_description
        
        return data


@dataclass
class BDDFeature:
    """BDD Feature representation."""
    
    name: str
    description: Optional[str] = None
    file_path: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    background: Optional["BDDScenario"] = None
    scenarios: List["BDDScenario"] = field(default_factory=list)
    
    def to_section(self) -> TestSection:
        """Convert BDD feature to TestRail section."""
        return TestSection(
            name=self.name,
            description=self.description,
            custom_feature_file=self.file_path,
            custom_feature_description=self.description
        )


@dataclass
class BDDScenario:
    """BDD Scenario representation."""
    
    name: str
    type: str = "scenario"  # scenario, scenario_outline, background
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    examples: Optional[List[Dict[str, Any]]] = None
    feature: Optional[str] = None
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    
    def to_test_case(self, section_id: int) -> TestCase:
        """Convert BDD scenario to TestRail test case."""
        # Extract requirements from tags
        requirements = []
        capabilities = {}
        
        for tag in self.tags:
            if tag.startswith("@req:"):
                requirements.append(tag[5:])
            elif tag.startswith("@cap:"):
                cap_str = tag[5:]
                if "=" in cap_str:
                    key, value = cap_str.split("=", 1)
                    capabilities[key] = value
        
        # Generate Gherkin text
        gherkin_lines = []
        if self.type == "scenario_outline":
            gherkin_lines.append(f"Scenario Outline: {self.name}")
        else:
            gherkin_lines.append(f"Scenario: {self.name}")
        
        for step in self.steps:
            gherkin_lines.append(f"  {step}")
        
        if self.examples:
            gherkin_lines.append("")
            gherkin_lines.append("  Examples:")
            if self.examples:
                headers = list(self.examples[0].keys())
                gherkin_lines.append("    | " + " | ".join(headers) + " |")
                for example in self.examples:
                    values = [str(example.get(h, "")) for h in headers]
                    gherkin_lines.append("    | " + " | ".join(values) + " |")
        
        gherkin = "\n".join(gherkin_lines)
        
        return TestCase(
            title=self.name,
            section_id=section_id,
            type_id=TestType.BDD,
            custom_gherkin=gherkin,
            custom_scenario_type=self.type,
            custom_feature_file=self.file_path,
            custom_tags=self.tags,
            custom_requirements=requirements,
            custom_capabilities=capabilities,
            custom_automation_id=f"{self.feature}:{self.name}" if self.feature else self.name
        )