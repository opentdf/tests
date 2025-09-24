"""Service Locator for dynamic service resolution."""

import os
from typing import Dict, Optional, Any
from dataclasses import dataclass
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class ServiceConfig:
    """Configuration for a service endpoint."""
    
    name: str
    endpoint: str
    port: Optional[int] = None
    protocol: str = "http"
    credentials: Optional[Dict[str, str]] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    @property
    def url(self) -> str:
        """Get the full URL for the service."""
        if self.port:
            return f"{self.protocol}://{self.endpoint}:{self.port}"
        return f"{self.protocol}://{self.endpoint}"


class SecretManager:
    """Manages secrets and credentials for services."""
    
    def __init__(self, env: str = "local"):
        self.env = env
        self._secrets = {}
        self._load_secrets()
    
    def _load_secrets(self):
        """Load secrets from environment variables or secret store."""
        # In production, this would integrate with a real secret manager
        # For now, load from environment variables
        for key, value in os.environ.items():
            if key.startswith("TEST_SECRET_"):
                secret_name = key.replace("TEST_SECRET_", "").lower()
                self._secrets[secret_name] = value
    
    def get_credentials(self, service_key: str) -> Optional[Dict[str, str]]:
        """Get credentials for a service."""
        # Check for service-specific credentials
        username_key = f"{service_key}_username"
        password_key = f"{service_key}_password"
        api_key = f"{service_key}_api_key"
        
        creds = {}
        if username_key in self._secrets:
            creds["username"] = self._secrets[username_key]
        if password_key in self._secrets:
            creds["password"] = self._secrets[password_key]
        if api_key in self._secrets:
            creds["api_key"] = self._secrets[api_key]
        
        return creds if creds else None


class ServiceNotFoundError(Exception):
    """Raised when a requested service is not found."""
    pass


class ServiceLocator:
    """Resolves service endpoints and credentials at runtime."""
    
    def __init__(self, env: str = None):
        self.env = env or os.getenv("TEST_ENV", "local")
        self.registry: Dict[str, ServiceConfig] = {}
        self.secret_manager = SecretManager(self.env)
        self._load_service_registry()
    
    def _load_service_registry(self):
        """Load service registry from configuration."""
        # Try to load from config file
        config_path = Path(__file__).parent.parent.parent / "config" / f"services.{self.env}.json"
        
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                for service_name, service_data in config.get("services", {}).items():
                    self.register_service(
                        service_name,
                        ServiceConfig(**service_data)
                    )
        
        # Load default services for OpenTDF
        self._load_default_services()
    
    def _load_default_services(self):
        """Load default OpenTDF services."""
        defaults = {
            "kas": ServiceConfig(
                name="kas",
                endpoint=os.getenv("KAS_URL", "localhost"),
                port=int(os.getenv("KAS_PORT", "8080")),
                protocol="http"
            ),
            "keycloak": ServiceConfig(
                name="keycloak",
                endpoint=os.getenv("KEYCLOAK_URL", "localhost"),
                port=int(os.getenv("KEYCLOAK_PORT", "8888")),
                protocol="http"
            ),
            "platform": ServiceConfig(
                name="platform",
                endpoint=os.getenv("PLATFORM_URL", "localhost"),
                port=int(os.getenv("PLATFORM_PORT", "8080")),
                protocol="http"
            ),
            "postgres": ServiceConfig(
                name="postgres",
                endpoint=os.getenv("POSTGRES_HOST", "localhost"),
                port=int(os.getenv("POSTGRES_PORT", "5432")),
                protocol="postgresql"
            )
        }
        
        for name, config in defaults.items():
            if name not in self.registry:
                self.registry[name] = config
    
    def resolve(self, service_name: str, role: str = "default") -> ServiceConfig:
        """
        Resolve service configuration.
        
        Args:
            service_name: Name of the service to resolve
            role: Role/profile for the service (e.g., "admin", "user")
        
        Returns:
            ServiceConfig with resolved endpoint and credentials
        
        Raises:
            ServiceNotFoundError: If service is not registered
        """
        # Check for role-specific service first
        role_service_name = f"{service_name}_{role}" if role != "default" else service_name
        
        if role_service_name in self.registry:
            service = self.registry[role_service_name]
        elif service_name in self.registry:
            service = self.registry[service_name]
        else:
            raise ServiceNotFoundError(f"Service {service_name} not registered")
        
        # Resolve credentials
        service.credentials = self.secret_manager.get_credentials(role_service_name)
        
        # Apply environment-specific overrides
        self._apply_env_overrides(service)
        
        logger.debug(f"Resolved service {service_name} ({role}): {service.url}")
        return service
    
    def _apply_env_overrides(self, service: ServiceConfig):
        """Apply environment-specific overrides to service config."""
        # Check for environment variable overrides
        env_endpoint = os.getenv(f"{service.name.upper()}_ENDPOINT")
        env_port = os.getenv(f"{service.name.upper()}_PORT")
        env_protocol = os.getenv(f"{service.name.upper()}_PROTOCOL")
        
        if env_endpoint:
            service.endpoint = env_endpoint
        if env_port:
            service.port = int(env_port)
        if env_protocol:
            service.protocol = env_protocol
    
    def register_service(self, name: str, config: ServiceConfig):
        """Register a new service for discovery."""
        self.registry[name] = config
        logger.info(f"Registered service: {name}")
    
    def list_services(self) -> Dict[str, str]:
        """List all registered services and their URLs."""
        return {name: config.url for name, config in self.registry.items()}
    
    def health_check(self, service_name: str) -> bool:
        """Check if a service is healthy/reachable."""
        try:
            service = self.resolve(service_name)
            # In a real implementation, make an actual health check request
            # For now, just check if we can resolve it
            return service is not None
        except ServiceNotFoundError:
            return False