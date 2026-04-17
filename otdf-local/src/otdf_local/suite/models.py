"""Pydantic models for the X-Test suite configuration."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SDKVersion(BaseModel):
    """Configuration for an SDK version."""

    tag: str
    sha: Optional[str] = None
    source: Optional[str] = None  # For Go: "platform" or "standalone"
    alias: Optional[str] = None
    head: bool = False


class PlatformVersion(BaseModel):
    """Configuration for a platform version."""

    tag: str
    sha: Optional[str] = None
    ec_tdf_enabled: bool = True
    # Optional JSON string of extra keys, or path to extra-keys.json
    extra_keys: Optional[str] = None


class TestJob(BaseModel):
    """Configuration for a test execution job."""

    name: str
    pytest_args: List[str] = Field(default_factory=list)
    requires_kas: bool = False
    focus_sdk: str = "all"


class SuiteConfig(BaseModel):
    """Root configuration for a test suite (or shard)."""

    platforms: List[PlatformVersion]
    sdks: Dict[str, List[SDKVersion]]
    jobs: List[TestJob]
