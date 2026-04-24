"""User-specified feature overrides for platform config."""

from pathlib import Path
from typing import Any

from otdf_local.utils.yaml import load_yaml, save_yaml, set_nested

# Maps CLI feature name -> (yaml_path, description)
FEATURES: dict[str, tuple[str, str]] = {
    "ec-wrap": (
        "services.kas.preview.ec_tdf_enabled",
        "EC-wrapped TDF support",
    ),
    "key-management": (
        "services.kas.preview.key_management",
        "Key management service",
    ),
    "hpqt": (
        "services.kas.preview.hybrid_tdf_enabled",
        "Hybrid Post Quantum/Traditional KEM Algorithms"
    )
}


def _overrides_path(xtest_root: Path) -> Path:
    """Path to feature overrides file. Lives in tmp/ but outside config/ so it survives --clean."""
    return xtest_root / "tmp" / "feature-overrides.yaml"


def load_overrides(xtest_root: Path) -> dict[str, bool]:
    """Load current feature overrides. Returns empty dict if none set."""
    path = _overrides_path(xtest_root)
    if not path.exists():
        return {}
    data = load_yaml(path)
    return dict(data) if data else {}


def save_overrides(xtest_root: Path, overrides: dict[str, bool]) -> None:
    """Persist feature overrides to disk."""
    path = _overrides_path(xtest_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_yaml(path, overrides)


def apply_overrides(config_data: Any, overrides: dict[str, bool]) -> None:
    """Apply feature overrides to a loaded YAML config object (in-place)."""
    for feature, enabled in overrides.items():
        if feature in FEATURES:
            yaml_path, _ = FEATURES[feature]
            set_nested(config_data, yaml_path, enabled)
