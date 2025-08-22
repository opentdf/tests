"""Pydantic models for the test framework.

This module provides type-safe, validated data models for the test framework.
Using Pydantic ensures fail-fast behavior and clear contracts.
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
from pydantic import BaseModel, Field, field_validator, ConfigDict


class OperationMode(str, Enum):
    """Valid operation modes for testing."""
    ONLINE = "online"
    OFFLINE = "offline"
    STANDALONE = "standalone"
    HYBRID = "hybrid"


class TestStatus(str, Enum):
    """Test execution status."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    PENDING = "pending"


class SDKType(str, Enum):
    """Supported SDK types."""
    GO = "go"
    JAVA = "java"
    JS = "js"
    SWIFT = "swift"
    PYTHON = "py"


class ContainerFormat(str, Enum):
    """TDF container formats."""
    NANO = "nano"
    ZTDF = "ztdf"
    ZTDF_ECWRAP = "ztdf-ecwrap"
    NANO_WITH_ECDSA = "nano-with-ecdsa"


class EncryptionType(str, Enum):
    """Encryption algorithms."""
    AES256GCM = "aes256gcm"
    CHACHA20POLY1305 = "chacha20poly1305"


class ProfileConfig(BaseModel):
    """Profile configuration settings."""
    
    model_config = ConfigDict(extra="forbid")
    
    roles: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    selection_strategy: str = Field(default="pairwise", pattern="^(pairwise|exhaustive|minimal)$")
    max_variants: int = Field(default=50, ge=1, le=1000)
    timeouts: Dict[str, int] = Field(default_factory=lambda: {"test": 60, "suite": 600})
    parallel_workers: int = Field(default=4, ge=1, le=32)
    
    @field_validator("timeouts")
    @classmethod
    def validate_timeouts(cls, v: Dict[str, int]) -> Dict[str, int]:
        """Ensure timeouts are positive."""
        for key, value in v.items():
            if value <= 0:
                raise ValueError(f"Timeout {key} must be positive, got {value}")
        return v


class ProfilePolicies(BaseModel):
    """Profile test policies."""
    
    model_config = ConfigDict(extra="forbid")
    
    waivers: List[Dict[str, str]] = Field(default_factory=list)
    expected_skips: List[Dict[str, str]] = Field(default_factory=list)
    severities: Dict[str, str] = Field(default_factory=dict)
    retry_on_failure: bool = Field(default=False)
    max_retries: int = Field(default=3, ge=0, le=10)


class Capability(BaseModel):
    """A single capability definition."""
    
    model_config = ConfigDict(extra="forbid")
    
    key: str = Field(..., min_length=1)
    values: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    required: bool = Field(default=False)
    
    @field_validator("key")
    @classmethod
    def validate_key(cls, v: str) -> str:
        """Ensure capability key is lowercase."""
        return v.lower()


class Profile(BaseModel):
    """Test profile with capabilities and configuration."""
    
    model_config = ConfigDict(extra="forbid")
    
    id: str = Field(..., min_length=1, pattern="^[a-z0-9-]+$")
    capabilities: Dict[str, List[str]] = Field(default_factory=dict)
    config: ProfileConfig = Field(default_factory=ProfileConfig)
    policies: ProfilePolicies = Field(default_factory=ProfilePolicies)
    description: Optional[str] = None
    parent: Optional[str] = None  # For profile inheritance
    
    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Ensure profile ID follows naming convention."""
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"Profile ID must be alphanumeric with hyphens, got: {v}")
        return v
    
    def has_capability(self, key: str, value: Optional[str] = None) -> bool:
        """Check if profile has a capability."""
        if key not in self.capabilities:
            return False
        if value is None:
            return True
        return value in self.capabilities[key]
    
    def should_skip_test(self, required_capabilities: Dict[str, str]) -> Optional[str]:
        """Check if test should be skipped based on capabilities."""
        for cap_key, cap_value in required_capabilities.items():
            if not self.has_capability(cap_key, cap_value):
                return f"Missing capability: {cap_key}={cap_value}"
        return None


class ServiceConfig(BaseModel):
    """Service configuration for ServiceLocator."""
    
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(..., min_length=1)
    url: str = Field(..., pattern="^https?://")
    health_check_path: Optional[str] = Field(default="/health")
    timeout: int = Field(default=30, ge=1)
    retries: int = Field(default=3, ge=0)
    credentials: Optional[Dict[str, str]] = None
    headers: Dict[str, str] = Field(default_factory=dict)
    
    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Ensure URL is valid."""
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"URL must start with http:// or https://, got: {v}")
        return v.rstrip("/")


class Evidence(BaseModel):
    """Test execution evidence."""
    
    model_config = ConfigDict(extra="allow")
    
    req_id: Optional[str] = None
    profile_id: str
    variant: str = Field(default="default")
    commit_sha: Optional[str] = None
    start_timestamp: datetime
    end_timestamp: Optional[datetime] = None
    status: TestStatus
    duration_seconds: Optional[float] = None
    
    # Artifacts
    logs: List[Path] = Field(default_factory=list)
    screenshots: List[Path] = Field(default_factory=list)
    attachments: List[Path] = Field(default_factory=list)
    artifact_url: Optional[str] = None
    
    # Error information
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    
    # Metadata
    test_name: str
    test_file: Optional[Path] = None
    capabilities_tested: Dict[str, str] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    
    def to_json_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        data = self.model_dump(exclude_none=True)
        # Convert Path objects to strings
        for field in ["logs", "screenshots", "attachments"]:
            if field in data:
                data[field] = [str(p) for p in data[field]]
        if "test_file" in data:
            data["test_file"] = str(data["test_file"])
        # Convert datetime to ISO format
        if "start_timestamp" in data:
            data["start_timestamp"] = data["start_timestamp"].isoformat()
        if "end_timestamp" in data:
            data["end_timestamp"] = data["end_timestamp"].isoformat()
        return data


class TestCase(BaseModel):
    """Test case metadata."""
    
    model_config = ConfigDict(extra="forbid")
    
    id: str = Field(..., min_length=1)
    name: str
    file_path: Path
    requirement_id: Optional[str] = None
    required_capabilities: Dict[str, str] = Field(default_factory=dict)
    tags: Set[str] = Field(default_factory=set)
    skip_reason: Optional[str] = None
    estimated_duration: float = Field(default=1.0, ge=0)
    
    def should_run_with_profile(self, profile: Profile) -> bool:
        """Check if test should run with given profile."""
        skip_reason = profile.should_skip_test(self.required_capabilities)
        return skip_reason is None


class TestRun(BaseModel):
    """Test run metadata."""
    
    model_config = ConfigDict(extra="allow")
    
    id: str = Field(..., min_length=1)
    profile_id: str
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    total_tests: int = Field(default=0, ge=0)
    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    error: int = Field(default=0, ge=0)
    artifacts_dir: Optional[Path] = None
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate run duration."""
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
    
    @property
    def pass_rate(self) -> float:
        """Calculate pass rate percentage."""
        if self.total_tests == 0:
            return 0.0
        return (self.passed / self.total_tests) * 100


class CapabilityCatalog(BaseModel):
    """Catalog of all available capabilities."""
    
    model_config = ConfigDict(extra="forbid")
    
    version: str = Field(default="1.0.0")
    capabilities: Dict[str, Capability] = Field(default_factory=dict)
    
    def validate_capability(self, key: str, value: str) -> bool:
        """Validate a capability key-value pair."""
        if key not in self.capabilities:
            return False
        cap = self.capabilities[key]
        return value in cap.values
    
    def get_all_keys(self) -> List[str]:
        """Get all capability keys."""
        return list(self.capabilities.keys())
    
    def get_values_for_key(self, key: str) -> List[str]:
        """Get valid values for a capability key."""
        if key in self.capabilities:
            return self.capabilities[key].values
        return []