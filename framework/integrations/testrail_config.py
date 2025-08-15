"""TestRail configuration management."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any
import yaml


@dataclass
class TestRailConfig:
    """TestRail configuration settings."""
    
    base_url: str
    username: str
    api_key: str
    project_id: int
    suite_id: Optional[int] = None
    milestone_id: Optional[int] = None
    run_name_template: str = "Automated Test Run - {timestamp}"
    
    # BDD-specific settings
    bdd_section_id: Optional[int] = None
    preserve_gherkin: bool = True
    create_sections_from_features: bool = True
    
    # Custom field mappings
    custom_fields: Dict[str, str] = None
    
    # Performance settings
    batch_size: int = 100
    max_retries: int = 3
    retry_delay: float = 1.0
    request_timeout: int = 30
    
    # Caching settings
    enable_cache: bool = True
    cache_ttl: int = 300  # 5 minutes
    
    def __post_init__(self):
        """Initialize custom fields if not provided."""
        if self.custom_fields is None:
            self.custom_fields = {
                "capabilities": "custom_capabilities",
                "requirements": "custom_requirements",
                "profile": "custom_profile",
                "artifact_url": "custom_artifact_url",
                "commit_sha": "custom_commit_sha",
                "gherkin": "custom_gherkin_text"
            }
    
    @classmethod
    def from_env(cls) -> "TestRailConfig":
        """Load configuration from environment variables."""
        return cls(
            base_url=os.environ.get("TESTRAIL_URL", "https://virtru.testrail.io"),
            username=os.environ.get("TESTRAIL_USERNAME", ""),
            api_key=os.environ.get("TESTRAIL_API_KEY", ""),
            project_id=int(os.environ.get("TESTRAIL_PROJECT_ID", "1")),
            suite_id=int(os.environ.get("TESTRAIL_SUITE_ID", "0")) or None,
            milestone_id=int(os.environ.get("TESTRAIL_MILESTONE_ID", "0")) or None,
            bdd_section_id=int(os.environ.get("TESTRAIL_BDD_SECTION_ID", "0")) or None,
            preserve_gherkin=os.environ.get("TESTRAIL_PRESERVE_GHERKIN", "true").lower() == "true",
            create_sections_from_features=os.environ.get("TESTRAIL_CREATE_SECTIONS", "true").lower() == "true",
            batch_size=int(os.environ.get("TESTRAIL_BATCH_SIZE", "100")),
            max_retries=int(os.environ.get("TESTRAIL_MAX_RETRIES", "3")),
            retry_delay=float(os.environ.get("TESTRAIL_RETRY_DELAY", "1.0")),
            request_timeout=int(os.environ.get("TESTRAIL_REQUEST_TIMEOUT", "30")),
            enable_cache=os.environ.get("TESTRAIL_ENABLE_CACHE", "true").lower() == "true",
            cache_ttl=int(os.environ.get("TESTRAIL_CACHE_TTL", "300"))
        )
    
    @classmethod
    def from_yaml(cls, config_path: Path) -> "TestRailConfig":
        """Load configuration from YAML file."""
        with open(config_path) as f:
            config_data = yaml.safe_load(f)
        
        testrail_config = config_data.get("testrail", {})
        
        return cls(
            base_url=testrail_config.get("base_url", "https://virtru.testrail.io"),
            username=testrail_config.get("username", ""),
            api_key=testrail_config.get("api_key", ""),
            project_id=testrail_config.get("project_id", 1),
            suite_id=testrail_config.get("suite_id"),
            milestone_id=testrail_config.get("milestone_id"),
            bdd_section_id=testrail_config.get("bdd_section_id"),
            preserve_gherkin=testrail_config.get("preserve_gherkin", True),
            create_sections_from_features=testrail_config.get("create_sections_from_features", True),
            custom_fields=testrail_config.get("custom_fields"),
            batch_size=testrail_config.get("batch_size", 100),
            max_retries=testrail_config.get("max_retries", 3),
            retry_delay=testrail_config.get("retry_delay", 1.0),
            request_timeout=testrail_config.get("request_timeout", 30),
            enable_cache=testrail_config.get("enable_cache", True),
            cache_ttl=testrail_config.get("cache_ttl", 300)
        )
    
    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "TestRailConfig":
        """
        Load configuration from file or environment.
        
        Priority:
        1. Provided config file
        2. testrail.yaml in current directory
        3. Environment variables
        """
        if config_path and config_path.exists():
            return cls.from_yaml(config_path)
        
        default_config = Path("testrail.yaml")
        if default_config.exists():
            return cls.from_yaml(default_config)
        
        return cls.from_env()
    
    def validate(self) -> bool:
        """Validate required configuration fields."""
        if not self.base_url:
            raise ValueError("TestRail base URL is required")
        
        if not self.username:
            raise ValueError("TestRail username is required")
        
        if not self.api_key:
            raise ValueError("TestRail API key is required")
        
        if self.project_id <= 0:
            raise ValueError("Valid TestRail project ID is required")
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "base_url": self.base_url,
            "username": self.username,
            "project_id": self.project_id,
            "suite_id": self.suite_id,
            "milestone_id": self.milestone_id,
            "run_name_template": self.run_name_template,
            "bdd_section_id": self.bdd_section_id,
            "preserve_gherkin": self.preserve_gherkin,
            "create_sections_from_features": self.create_sections_from_features,
            "custom_fields": self.custom_fields,
            "batch_size": self.batch_size,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "request_timeout": self.request_timeout,
            "enable_cache": self.enable_cache,
            "cache_ttl": self.cache_ttl
        }