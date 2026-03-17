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
    "Service",
    "ServiceInfo",
    "ServiceType",
    "DockerService",
    "get_docker_service",
    "KASManager",
    "KASService",
    "get_kas_manager",
    "PlatformService",
    "get_platform_service",
    "Provisioner",
    "ProvisionResult",
    "get_provisioner",
]
