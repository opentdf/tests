"""Export an SDK capability snapshot (supports.json) for the Pages report.

Usage (from xtest/ cwd, after the SDK CLI dist is built):
  uv run python -m reporting.export_supports --sdk python \\
    --sdk-ref "$PYTHON_REF" --out test-results

Probes ``sdk/<sdk>/dist/<version>/cli.sh supports <feature>`` for every
known feature and writes supports.json + meta.json under
``<out>/report-<sdk>-<os>/``, which reporting.generate_site consumes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

FEATURES = [
    "assertions",
    "assertion_verification",
    "attribute_traversal",
    "audit_logging",
    "autoconfigure",
    "better-messages-2024",
    "bulk_rewrap",
    "connectrpc",
    "dpop",
    "dpop_nonce_challenge",
    "ecwrap",
    "hexless",
    "hexaflexible",
    "kasallowlist",
    "key_management",
    "mechanism-rsa-4096",
    "mechanism-ec-curves-384-521",
    "mechanism-xwing",
    "mechanism-secpmlkem",
    "mechanism-mlkem",
    "ns_grants",
    "obligations",
]


def probe(cli: Path, feature: str) -> str:
    try:
        result = subprocess.run(
            [str(cli), "supports", feature], capture_output=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"error:{e}"
    if result.returncode == 0:
        return "supported"
    if result.returncode == 1:
        return "unsupported"
    return "unknown"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sdk", required=True, help="SDK name, e.g. python")
    p.add_argument(
        "--version", default="main", help="dist channel under sdk/<sdk>/dist/"
    )
    p.add_argument("--sdk-ref", default=os.environ.get("SDK_REF", "latest"))
    p.add_argument(
        "--os",
        dest="os_name",
        default=os.environ.get("RUNNER_OS_LABEL", "ubuntu-latest"),
    )
    p.add_argument("--tier", default="kas-ready")
    p.add_argument("--out", type=Path, default=Path("test-results"))
    args = p.parse_args()

    cli = Path("sdk") / args.sdk / "dist" / args.version / "cli.sh"
    supports = {feature: probe(cli, feature) for feature in FEATURES}

    snapshot = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "sdk": args.sdk,
        "sdk_ref": args.sdk_ref,
        "platform_ref": os.environ.get("PLATFORM_REF", "latest"),
        "go_channel": os.environ.get("GO_CHANNEL", "latest"),
        "tier": args.tier,
        "supports": supports,
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "repo": os.environ.get("GITHUB_REPOSITORY"),
    }
    dest = args.out / f"report-{args.sdk}-{args.os_name}"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "supports.json").write_text(json.dumps(snapshot, indent=2))
    (dest / "meta.json").write_text(
        json.dumps(
            {
                "sdk": args.sdk,
                "os": args.os_name,
                "run_id": os.environ.get("GITHUB_RUN_ID"),
            },
            indent=2,
        )
    )
    print(json.dumps(snapshot, indent=2))


if __name__ == "__main__":
    main()
