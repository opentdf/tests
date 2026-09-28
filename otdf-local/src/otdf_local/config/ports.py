"""Port constants for all services."""

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class Ports:
    """Port configuration for all services."""

    # Docker services
    KEYCLOAK: int = 8888
    POSTGRES: int = 5432

    # Platform
    PLATFORM: int = 8080

    # Offset of each KAS port from `base` (which is the platform port).
    # The defaults at base=8080 reproduce the historical 8181/8282/... layout.
    KAS_OFFSETS: ClassVar[dict[str, int]] = {
        "alpha": 101,
        "beta": 202,
        "gamma": 303,
        "delta": 404,
        "km1": 505,
        "km2": 606,
    }

    @classmethod
    def get_kas_port(cls, name: str, *, base: int = 8080) -> int:
        offset = cls.KAS_OFFSETS.get(name)
        if offset is None:
            raise ValueError(f"Unknown KAS instance: {name}")
        return base + offset

    @classmethod
    def platform_port_for(cls, base: int) -> int:
        """Return the platform port for a given `base`. Trivially `base` today."""
        return base

    @classmethod
    def all_kas_names(cls) -> list[str]:
        """Return all KAS instance names."""
        return list(cls.KAS_OFFSETS.keys())

    @classmethod
    def standard_kas_names(cls) -> list[str]:
        """Return standard (non-key-management) KAS instance names."""
        return ["alpha", "beta", "gamma", "delta"]

    @classmethod
    def km_kas_names(cls) -> list[str]:
        """Return key management KAS instance names."""
        return ["km1", "km2"]

    @classmethod
    def is_km_kas(cls, name: str) -> bool:
        """Check if a KAS instance is a key management instance."""
        return name in cls.km_kas_names()
