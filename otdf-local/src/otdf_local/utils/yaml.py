"""YAML manipulation utilities using ruamel.yaml."""

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

# Configure YAML instance to preserve formatting
_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.width = 120


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, preserving comments and formatting.

    Raises:
        OSError: The file cannot be read.
        ValueError: The file is not valid YAML. ruamel's own errors derive
            from neither, so callers catching (OSError, ValueError) would
            otherwise miss them -- and they don't name the file.
    """
    with open(path) as f:
        try:
            return _yaml.load(f) or {}
        except YAMLError as e:
            raise ValueError(f"{path} is not valid YAML: {e}") from e


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    """Save data to a YAML file, preserving formatting.

    Writes a sibling temp file and renames it over `path`, so an interrupted
    write leaves the previous contents rather than a truncated file.
    """
    partial = path.with_name(path.name + ".tmp")
    with open(partial, "w") as f:
        _yaml.dump(data, f)
    partial.replace(path)


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

    Creates intermediate dicts as needed, including in place of an empty
    (null) value. Raises ValueError if an intermediate value is a scalar or
    list, which cannot hold the key.
    """
    keys = path.split(".")
    current = data
    for i, key in enumerate(keys[:-1]):
        if current.get(key) is None:
            current[key] = {}
        elif not isinstance(current[key], dict):
            parent = ".".join(keys[: i + 1])
            raise ValueError(
                f"Cannot set {path}: {parent} is a {type(current[key]).__name__}, "
                "not a mapping"
            )
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


def append_to_list(data: dict[str, Any], path: str, items: list[Any]) -> None:
    """Append items to a list at a nested path.

    Args:
        data: The dictionary to modify
        path: Dot-separated path to the list
        items: Items to append
    """
    current_list = get_nested(data, path, [])
    if not isinstance(current_list, list):
        current_list = []

    # Check for duplicates by kid if items are dicts with kid
    existing_kids = {
        item.get("kid")
        for item in current_list
        if isinstance(item, dict) and "kid" in item
    }
    for item in items:
        if isinstance(item, dict) and "kid" in item:
            if item["kid"] not in existing_kids:
                current_list.append(item)
                existing_kids.add(item["kid"])
        else:
            current_list.append(item)

    set_nested(data, path, current_list)


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
