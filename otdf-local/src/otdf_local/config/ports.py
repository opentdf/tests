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

    # Mapping from KAS name to class attribute name
    _KAS_NAMES: dict[str, str] = {
        "alpha": "KAS_ALPHA",
        "beta": "KAS_BETA",
        "gamma": "KAS_GAMMA",
        "delta": "KAS_DELTA",
        "km1": "KAS_KM1",
        "km2": "KAS_KM2",
    }

    @classmethod
    def get_kas_port(cls, name: str) -> int:
        """Get port for a KAS instance by name."""
        attr = cls._KAS_NAMES.get(name)
        if attr is None:
            raise ValueError(f"Unknown KAS instance: {name}")
        return getattr(cls, attr)

    @classmethod
    def all_kas_names(cls) -> list[str]:
        """Return all KAS instance names."""
        return list(cls._KAS_NAMES.keys())

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
