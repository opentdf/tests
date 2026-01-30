"""Port constants for all services."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Ports:
    """Port configuration for all services."""

    # Docker services
    KEYCLOAK: int = 8888
    POSTGRES: int = 5432

    # Platform
    PLATFORM: int = 8080

    # KAS instances
    KAS_ALPHA: int = 8181
    KAS_BETA: int = 8282
    KAS_GAMMA: int = 8383
    KAS_DELTA: int = 8484
    KAS_KM1: int = 8585
    KAS_KM2: int = 8686

    @classmethod
    def get_kas_port(cls, name: str) -> int:
        """Get port for a KAS instance by name."""
        mapping = {
            "alpha": cls.KAS_ALPHA,
            "beta": cls.KAS_BETA,
            "gamma": cls.KAS_GAMMA,
            "delta": cls.KAS_DELTA,
            "km1": cls.KAS_KM1,
            "km2": cls.KAS_KM2,
        }
        if name not in mapping:
            raise ValueError(f"Unknown KAS instance: {name}")
        return mapping[name]

    @classmethod
    def all_kas_names(cls) -> list[str]:
        """Return all KAS instance names."""
        return ["alpha", "beta", "gamma", "delta", "km1", "km2"]

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
