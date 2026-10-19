"""Publish a rendered benchmark summary, with or without an artifact URL.

pytest writes the summary as a template before the artifact exists, because
the artifact contains the run's own output. CI uploads it, gets a URL back,
and calls this to fill the URL in; a local run has no URL, and gets the same
summary with those links removed. Either way no placeholder survives.

Usage::

    python -m perf.publish SUMMARY_TEMPLATE [--artifact-url URL]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from perf.presentation import publish


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish a rendered benchmark summary template."
    )
    parser.add_argument("template", type=Path)
    parser.add_argument("--artifact-url", default="")
    args = parser.parse_args(argv)
    sys.stdout.write(publish(args.template.read_text(), args.artifact_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
