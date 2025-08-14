"""Profile management for test configuration."""

import yaml
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from itertools import combinations
import logging

logger = logging.getLogger(__name__)


@dataclass
class ProfileConfig:
    """Configuration settings for a test profile."""
    
    roles: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)
    selection: Dict[str, Any] = field(default_factory=dict)
    matrix: Dict[str, Any] = field(default_factory=dict)
    timeouts: Dict[str, int] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProfileConfig':
        """Create ProfileConfig from dictionary."""
        return cls(
            roles=data.get('roles', {}),
            selection=data.get('selection', {}),
            matrix=data.get('matrix', {}),
            timeouts=data.get('timeouts', {})
        )


@dataclass 
class ProfilePolicies:
    """Policy settings for a test profile."""
    
    waivers: List[Dict[str, str]] = field(default_factory=list)
    expected_skips: List[Dict[str, str]] = field(default_factory=list)
    severities: Dict[str, str] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProfilePolicies':
        """Create ProfilePolicies from dictionary."""
        return cls(
            waivers=data.get('waivers', []),
            expected_skips=data.get('expected_skips', []),
            severities=data.get('severities', {})
        )


@dataclass
class Profile:
    """Test profile configuration."""
    
    id: str
    capabilities: Dict[str, List[str]]
    config: ProfileConfig
    policies: ProfilePolicies
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def should_skip(self, test_name: str, capabilities: Dict[str, str]) -> Optional[str]:
        """
        Check if a test should be skipped based on policies.
        
        Args:
            test_name: Name of the test
            capabilities: Current capability values
        
        Returns:
            Skip reason if test should be skipped, None otherwise
        """
        for skip in self.policies.expected_skips:
            condition = skip.get('condition', '')
            reason = skip.get('reason', 'Policy skip')
            
            # Evaluate condition
            if self._evaluate_condition(condition, capabilities):
                return reason
        
        return None
    
    def is_waived(self, test_name: str) -> bool:
        """Check if a test failure is waived."""
        for waiver in self.policies.waivers:
            if waiver.get('test') == test_name:
                return True
        return False
    
    def get_severity(self, error_type: str) -> str:
        """Get severity level for an error type."""
        return self.policies.severities.get(error_type, 'medium')
    
    def _evaluate_condition(self, condition: str, capabilities: Dict[str, str]) -> bool:
        """
        Evaluate a skip condition.
        
        Simple evaluation of conditions like:
        - "sdk == 'swift' and format == 'ztdf-ecwrap'"
        """
        if not condition:
            return False
        
        # Replace capability references with actual values
        eval_condition = condition
        for key, value in capabilities.items():
            eval_condition = eval_condition.replace(key, f"'{value}'")
        
        try:
            # Safe evaluation with limited scope
            return eval(eval_condition, {"__builtins__": {}}, {})
        except Exception as e:
            logger.warning(f"Failed to evaluate condition '{condition}': {e}")
            return False


class CapabilityCatalog:
    """Catalog of available capabilities and their values."""
    
    def __init__(self, catalog_path: Optional[Path] = None):
        self.catalog_path = catalog_path
        self.capabilities: Dict[str, Dict[str, Any]] = {}
        self._load_catalog()
    
    def _load_catalog(self):
        """Load capability catalog from file."""
        if not self.catalog_path or not self.catalog_path.exists():
            # No default catalog - must have capability-catalog.yaml
            logger.error(f"Capability catalog not found at {self.catalog_path}")
            self.capabilities = {}
            return
        
        with open(self.catalog_path) as f:
            if self.catalog_path.suffix == '.yaml':
                data = yaml.safe_load(f)
            else:
                data = json.load(f)
        
        self.capabilities = data.get('capabilities', {})
    
    def validate_capability(self, key: str, value: str) -> bool:
        """Validate a capability key-value pair."""
        if key not in self.capabilities:
            logger.warning(f"Unknown capability key: {key}")
            return False
        
        cap_def = self.capabilities[key]
        valid_values = cap_def.get('values', [])
        
        if valid_values and value not in valid_values:
            logger.warning(f"Invalid value '{value}' for capability '{key}'. Valid values: {valid_values}")
            return False
        
        return True
    
    def get_capability_values(self, key: str) -> List[str]:
        """Get valid values for a capability."""
        if key in self.capabilities:
            return self.capabilities[key].get('values', [])
        return []


class ProfileManager:
    """Manages test profiles and capability matrices."""
    
    def __init__(self, profiles_dir: Path = None):
        """
        Initialize ProfileManager.
        
        Args:
            profiles_dir: Directory containing profile definitions
        """
        self.profiles_dir = profiles_dir or Path(__file__).parent.parent.parent / "profiles"
        self.capability_catalog = CapabilityCatalog(
            self.profiles_dir / "capability-catalog.yaml"
        )
        self._profiles_cache: Dict[str, Profile] = {}
    
    def load_profile(self, profile_id: str) -> Profile:
        """
        Load profile configuration from disk.
        
        Args:
            profile_id: Profile identifier
        
        Returns:
            Profile configuration
        """
        # Check cache first
        if profile_id in self._profiles_cache:
            return self._profiles_cache[profile_id]
        
        profile_path = self.profiles_dir / profile_id
        
        if not profile_path.exists():
            raise ValueError(f"Profile '{profile_id}' not found at {profile_path}")
        
        # Load configuration files
        capabilities = self._load_yaml(profile_path / "capabilities.yaml")
        config = self._load_yaml(profile_path / "config.yaml")
        policies = self._load_yaml(profile_path / "policies.yaml")
        
        # Load optional metadata
        metadata_path = profile_path / "metadata.yaml"
        metadata = self._load_yaml(metadata_path) if metadata_path.exists() else {}
        
        # Validate capabilities against catalog
        self._validate_capabilities(capabilities)
        
        profile = Profile(
            id=profile_id,
            capabilities=capabilities,
            config=ProfileConfig.from_dict(config),
            policies=ProfilePolicies.from_dict(policies),
            metadata=metadata
        )
        
        # Cache the profile
        self._profiles_cache[profile_id] = profile
        logger.info(f"Loaded profile: {profile_id}")
        
        return profile
    
    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """Load YAML file."""
        if not path.exists():
            return {}
        
        with open(path) as f:
            return yaml.safe_load(f) or {}
    
    def _validate_capabilities(self, capabilities: Dict[str, List[str]]):
        """Validate capabilities against catalog."""
        for key, values in capabilities.items():
            for value in values:
                if not self.capability_catalog.validate_capability(key, value):
                    logger.warning(f"Invalid capability: {key}={value}")
    
    def generate_capability_matrix(self, 
                                  capabilities: Dict[str, List[str]],
                                  strategy: str = "pairwise",
                                  max_variants: Optional[int] = None) -> List[Dict[str, str]]:
        """
        Generate test matrix from capability combinations.
        
        Args:
            capabilities: Dictionary of capability keys to value lists
            strategy: Matrix generation strategy ('exhaustive', 'pairwise', 'minimal')
            max_variants: Maximum number of variants to generate
        
        Returns:
            List of capability value combinations
        """
        if not capabilities:
            return [{}]
        
        if strategy == "exhaustive":
            matrix = self._generate_exhaustive(capabilities)
        elif strategy == "pairwise":
            matrix = self._generate_pairwise(capabilities)
        elif strategy == "minimal":
            matrix = self._generate_minimal(capabilities)
        else:
            raise ValueError(f"Unknown matrix strategy: {strategy}")
        
        # Limit variants if specified
        if max_variants and len(matrix) > max_variants:
            logger.info(f"Limiting matrix from {len(matrix)} to {max_variants} variants")
            matrix = matrix[:max_variants]
        
        return matrix
    
    def _generate_exhaustive(self, capabilities: Dict[str, List[str]]) -> List[Dict[str, str]]:
        """Generate all possible combinations (Cartesian product)."""
        from itertools import product
        
        keys = list(capabilities.keys())
        values = [capabilities[k] for k in keys]
        
        matrix = []
        for combo in product(*values):
            matrix.append(dict(zip(keys, combo)))
        
        return matrix
    
    def _generate_pairwise(self, capabilities: Dict[str, List[str]]) -> List[Dict[str, str]]:
        """Generate pairwise combinations for efficiency."""
        # Simplified pairwise generation
        # In production, use a proper pairwise algorithm like IPOG
        
        matrix = []
        keys = list(capabilities.keys())
        
        # Ensure all pairs are covered at least once
        for i, key1 in enumerate(keys):
            for j, key2 in enumerate(keys[i+1:], i+1):
                for val1 in capabilities[key1]:
                    for val2 in capabilities[key2]:
                        # Create a combination with these two values
                        combo = {}
                        combo[key1] = val1
                        combo[key2] = val2
                        
                        # Fill in other values (first value as default)
                        for k in keys:
                            if k not in combo:
                                combo[k] = capabilities[k][0]
                        
                        # Avoid duplicates
                        if combo not in matrix:
                            matrix.append(combo)
        
        # Ensure at least one combination with all first values
        if not matrix:
            matrix.append({k: v[0] for k, v in capabilities.items()})
        
        return matrix
    
    def _generate_minimal(self, capabilities: Dict[str, List[str]]) -> List[Dict[str, str]]:
        """Generate minimal set of combinations for smoke testing."""
        matrix = []
        
        # One combination with all first values
        matrix.append({k: v[0] for k, v in capabilities.items()})
        
        # One combination with all last values (if different)
        last_combo = {k: v[-1] for k, v in capabilities.items()}
        if last_combo != matrix[0]:
            matrix.append(last_combo)
        
        return matrix
    
    def list_profiles(self) -> List[str]:
        """List available profile IDs."""
        if not self.profiles_dir.exists():
            return []
        
        profiles = []
        for path in self.profiles_dir.iterdir():
            if path.is_dir() and (path / "capabilities.yaml").exists():
                profiles.append(path.name)
        
        return sorted(profiles)