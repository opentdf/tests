"""Version resolution via otdf-sdk-mgr subprocess calls."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from otdf_local.config.features import PlatformFeatures
from otdf_local.config.settings import Settings
from otdf_local.utils.console import print_error, print_info, print_warning
from otdf_local.utils.yaml import get_nested, load_yaml
from otdf_local.xtest.config import (
    Features,
    ResolvedVersion,
    XtestConfig,
    XtestInputs,
)


def _find_sdk_mgr_dir(settings: Settings) -> Path:
    """Locate the otdf-sdk-mgr directory (sibling of otdf-local in the repo)."""
    # Walk up from this file to find otdf-local root, then look for sibling
    otdf_local_dir = Path(__file__).resolve().parent.parent.parent.parent
    sdk_mgr = otdf_local_dir.parent / "otdf-sdk-mgr"
    if sdk_mgr.is_dir():
        return sdk_mgr
    # Try from xtest_root
    sdk_mgr = settings.xtest_root.parent / "otdf-sdk-mgr"
    if sdk_mgr.is_dir():
        return sdk_mgr
    raise FileNotFoundError(
        f"Could not find otdf-sdk-mgr directory. Checked: {otdf_local_dir.parent / 'otdf-sdk-mgr'}"
    )


def resolve_sdk_versions(
    sdk: str,
    refs: str,
    sdk_mgr_dir: Path,
    env_overrides: dict[str, str] | None = None,
) -> list[ResolvedVersion]:
    """Call otdf-sdk-mgr versions resolve for a single SDK type.

    Args:
        sdk: SDK type (platform, go, js, java)
        refs: Space-separated version refs (e.g., "main latest")
        sdk_mgr_dir: Path to otdf-sdk-mgr project
        env_overrides: Extra environment variables (e.g., OTDFCTL_SOURCE)

    Returns:
        List of ResolvedVersion objects
    """
    import os

    ref_args = refs.strip().split()
    cmd = [
        "uv",
        "run",
        "--project",
        str(sdk_mgr_dir),
        "otdf-sdk-mgr",
        "versions",
        "resolve",
        sdk,
        *ref_args,
    ]

    env = dict(os.environ)
    if env_overrides:
        env.update(env_overrides)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(sdk_mgr_dir),
        env=env,
    )

    if result.returncode != 0:
        return [
            ResolvedVersion(
                sdk=sdk,
                tag=refs,
                err=result.stderr.strip()
                or f"Process exited with code {result.returncode}",
            )
        ]

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return [ResolvedVersion(sdk=sdk, tag=refs, err=f"Invalid JSON output: {e}")]

    return [ResolvedVersion(**item) for item in data]


def detect_features(settings: Settings) -> Features:
    """Detect platform features from the local platform config and version."""
    features = Features()

    # Try to detect from platform version
    try:
        pf = PlatformFeatures.detect(settings.platform_dir)
        features.key_management = pf.supports("key_management")
        features.ec_tdf = pf.supports("ecwrap")
        # multikas is supported for main or version >= 0.4.x
        features.multikas = pf.semver >= (0, 4, 0)
    except Exception:
        pass

    # Also check config file for explicit settings
    try:
        config = load_yaml(settings.platform_config)
        ec_enabled = get_nested(config, "services.kas.preview.ec_tdf_enabled")
        if ec_enabled is not None:
            features.ec_tdf = bool(ec_enabled)
        km_enabled = get_nested(config, "services.kas.preview.key_management")
        if km_enabled is not None:
            features.key_management = bool(km_enabled)
    except Exception:
        pass

    return features


def resolve_all(inputs: XtestInputs, settings: Settings) -> XtestConfig:
    """Resolve all SDK versions and detect features, returning a complete config.

    Args:
        inputs: The version refs and options to resolve
        settings: otdf-local settings (for feature detection and path finding)

    Returns:
        A fully populated XtestConfig
    """
    sdk_mgr_dir = _find_sdk_mgr_dir(settings)
    print_info(f"Using otdf-sdk-mgr at: {sdk_mgr_dir}")

    resolved: dict[str, list[ResolvedVersion]] = {}
    has_errors = False

    # Resolve each SDK type
    sdk_refs = {
        "platform": inputs.platform_ref,
        "go": inputs.go_ref,
        "js": inputs.js_ref,
        "java": inputs.java_ref,
    }

    env_overrides: dict[str, str] = {}
    if inputs.otdfctl_source == "platform":
        env_overrides["OTDFCTL_SOURCE"] = "platform"

    for sdk, refs in sdk_refs.items():
        print_info(f"Resolving {sdk}: {refs}")
        sdk_env = env_overrides if sdk == "go" else None
        versions = resolve_sdk_versions(sdk, refs, sdk_mgr_dir, sdk_env)
        resolved[sdk] = versions

        for v in versions:
            if v.err:
                print_error(f"  Error resolving {sdk} {v.tag}: {v.err}")
                has_errors = True
            else:
                head_marker = " (head)" if v.head else ""
                print_info(f"  {v.tag} -> {v.sha[:7]}{head_marker}")

    if has_errors:
        print_warning("Some versions had errors; config may be incomplete")

    # Determine platform tag from resolved platform versions
    platform_tags = [v.tag for v in resolved.get("platform", []) if not v.err]
    platform_tag = platform_tags[0] if platform_tags else "main"

    # Detect features
    try:
        features = detect_features(settings)
    except Exception:
        features = Features()

    return XtestConfig(
        inputs=inputs,
        resolved=resolved,
        platform_tag=platform_tag,
        encrypt_sdk=inputs.focus_sdk if inputs.focus_sdk != "all" else "go",
        features=features,
    )
