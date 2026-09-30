"""Service management module for otdf-local."""

from otdf_local.services.base import Service, ServiceInfo, ServiceType
from otdf_local.services.docker import DockerService, get_docker_service
from otdf_local.services.kas import KASManager, KASService, get_kas_manager
from otdf_local.services.platform import PlatformService, get_platform_service
from otdf_local.services.provisioner import (
    Provisioner,
    ProvisionResult,
    get_provisioner,
)

__all__ = [
    "DockerService",
    "KASManager",
    "KASService",
    "PlatformService",
    "ProvisionResult",
    "Provisioner",
    "Service",
    "ServiceInfo",
    "ServiceType",
    "get_docker_service",
    "get_kas_manager",
    "get_platform_service",
    "get_provisioner",
]
