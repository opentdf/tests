"""Core framework components."""

from .service_locator import ServiceLocator, ServiceConfig, ServiceNotFoundError
from .profiles import Profile, ProfileManager, ProfileConfig, ProfilePolicies, CapabilityCatalog

__all__ = [
    'ServiceLocator',
    'ServiceConfig', 
    'ServiceNotFoundError',
    'Profile',
    'ProfileManager',
    'ProfileConfig',
    'ProfilePolicies',
    'CapabilityCatalog',
]