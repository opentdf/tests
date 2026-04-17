"""Post-checkout fixups for Go SDK (otdfctl) source trees.

Bridges client go.mod to server shared modules for head builds where
client and server share unreleased code.  Only applies to standalone
otdfctl checkouts — platform-source builds already have the modules.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from otdf_sdk_mgr.config import get_sdk_dir

# Platform modules that standalone otdfctl imports and that may need
# a local replace directive when testing against a head platform build.
PLATFORM_MODULES = [
    "lib/fixtures",
    "lib/ocrypto",
    "protocol/go",
    "sdk",
]


def go_fixup(
    platform_dir: Path,
    heads: list[str] | None = None,
    base_dir: Path | None = None,
) -> None:
    """Replace go.mod references to point at local platform checkout.

    Args:
        platform_dir: Absolute path to the platform checkout root
            (containing lib/, protocol/, sdk/).
        heads: JSON-decoded list of head version tags to process.
            If None, all subdirectories under *base_dir* are processed.
        base_dir: Directory containing per-version otdfctl source trees
            (e.g. ``xtest/sdk/go/src``).  Defaults to ``get_sdk_dir() / "go" / "src"``.
    """
    if base_dir is None:
        base_dir = get_sdk_dir() / "go" / "src"

    if not base_dir.exists():
        print(f"Base directory {base_dir} does not exist, nothing to fix.")
        return

    platform_dir = platform_dir.resolve()
    if not platform_dir.is_dir():
        raise FileNotFoundError(f"Platform directory does not exist: {platform_dir}")

    dirs_to_process: list[Path] = []
    if heads:
        for tag in heads:
            d = base_dir / tag
            if d.is_dir():
                dirs_to_process.append(d)
            else:
                print(f"Warning: head directory {d} does not exist, skipping.")
    else:
        for d in sorted(base_dir.iterdir()):
            if d.is_dir() and not d.name.endswith(".git"):
                dirs_to_process.append(d)

    if not dirs_to_process:
        print("No directories to process.")
        return

    for src_dir in dirs_to_process:
        if not (src_dir / "go.mod").exists():
            print(f"No go.mod in {src_dir}, skipping.")
            continue

        print(f"Applying go.mod replacements in {src_dir}...")
        for module in PLATFORM_MODULES:
            local_path = platform_dir / module
            if not local_path.is_dir():
                print(f"  Warning: {local_path} does not exist, skipping {module}")
                continue
            subprocess.run(
                [
                    "go",
                    "mod",
                    "edit",
                    "-replace",
                    f"github.com/opentdf/platform/{module}={local_path}",
                ],
                cwd=src_dir,
                check=True,
            )
            print(f"  Replaced github.com/opentdf/platform/{module} -> {local_path}")

        print(f"Running go mod tidy in {src_dir}...")
        subprocess.run(["go", "mod", "tidy"], cwd=src_dir, check=True)

    print("Go fixup complete.")
