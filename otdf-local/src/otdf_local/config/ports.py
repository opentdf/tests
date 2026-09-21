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

    # KAS instances
    KAS_ALPHA: int = 8181
    KAS_BETA: int = 8282
    KAS_GAMMA: int = 8383
    KAS_DELTA: int = 8484
    KAS_KM1: int = 8585
    KAS_KM2: int = 8686
    KAS_KM3: int = 8787

    # Mapping from KAS name to class attribute name
    _KAS_NAMES: ClassVar[dict[str, str]] = {
        "alpha": "KAS_ALPHA",
        "beta": "KAS_BETA",
        "gamma": "KAS_GAMMA",
        "delta": "KAS_DELTA",
        "km1": "KAS_KM1",
        "km2": "KAS_KM2",
        "km3": "KAS_KM3",
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
        return ["km1", "km2", "km3"]

    @classmethod
    def is_km_kas(cls, name: str) -> bool:
        """Check if a KAS instance is a key management instance."""
        return name in cls.km_kas_names()

    @classmethod
    def is_kao_uri_kas(cls, name: str) -> bool:
        """Whether this instance resolves managed keys by the KAO's KAS URI.

        Only km3. km1 is the negative control: xtest's
        test_decrypt_rejects_kao_kas_registration_when_disabled registers a key under
        km1's /kas URI and requires the rewrap to fail, which it only does while the
        setting stays off there. km2 leaves it off as well, but that is just the default
        -- no test asserts on it.
        """
        return name == "km3"
