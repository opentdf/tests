"""YAML manipulation utilities using ruamel.yaml."""

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

# Configure YAML instance to preserve formatting
_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.width = 120


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, preserving comments and formatting."""
    with open(path) as f:
        return _yaml.load(f) or {}


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    """Save data to a YAML file, preserving formatting."""
    with open(path, "w") as f:
        _yaml.dump(data, f)


def get_nested(data: dict[str, Any], path: str, default: Any = None) -> Any:
    """Get a nested value from a dict using dot notation.

    Args:
        data: The dictionary to search
        path: Dot-separated path (e.g., "services.kas.root_key")
        default: Value to return if path not found

    Returns:
        The value at the path, or default if not found
    """
    keys = path.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def set_nested(data: dict[str, Any], path: str, value: Any) -> None:
    """Set a nested value in a dict using dot notation.

    Args:
        data: The dictionary to modify
        path: Dot-separated path (e.g., "services.kas.root_key")
        value: The value to set

    Creates intermediate dicts as needed.
    """
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def update_yaml_file(path: Path, updates: dict[str, Any]) -> None:
    """Load a YAML file, apply updates, and save.

    Args:
        path: Path to the YAML file
        updates: Dict of dot-notation paths to values

    Example:
        update_yaml_file(
            config_path,
            {"server.port": 8080, "services.kas.root_key": "abc123"}
        )
    """
    data = load_yaml(path)
    for dot_path, value in updates.items():
        set_nested(data, dot_path, value)
    save_yaml(path, data)


def copy_yaml_with_updates(source: Path, dest: Path, updates: dict[str, Any]) -> None:
    """Copy a YAML file and apply updates to the copy.

    Args:
        source: Source YAML file path
        dest: Destination YAML file path
        updates: Dict of dot-notation paths to values
    """
    data = load_yaml(source)
    for dot_path, value in updates.items():
        set_nested(data, dot_path, value)
    save_yaml(dest, data)
