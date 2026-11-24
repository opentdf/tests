"""Corpus generator. Run from xtest/ with the platform and km1/km2 up, OT_ROOT_KEY
set and, for the Java writer, JAVA_HOME pointing at a JDK 21:

    uv run python -m corpus_gen write [--only GLOB ...]
    uv run python -m corpus_gen deks
    uv run python -m corpus_gen derive [--only tamper|zip]
    uv run python -m corpus_gen sidecars [--from DIR]
    uv run python -m corpus_gen install
    uv run python -m corpus_gen verdicts REC.jsonl...

Output lands in $XT_TMP_DIR/corpus_gen (default tmp/corpus_gen); see steps.py.
`derive`, `sidecars`, `install` and `verdicts` are offline. `derive` reads the
bases `write` left in scratch; `sidecars` carries validator fields and [sdk]
tables from the previous sidecars in DIR (default xtest/corpus); `install`
copies the stage into xtest/corpus; `verdicts` writes the [sdk] tables there
from `test_corpus.py --corpus-record` runs, one per platform.
"""

import argparse
import os
import sys
from pathlib import Path

import corpus
from corpus_gen import runtime, sidecars, steps, tamper, verdicts, zipcases


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="corpus_gen")
    sub = ap.add_subparsers(dest="cmd", required=True)
    write = sub.add_parser(
        "write", help="write the sdk-* fixtures and tamper bases into staging"
    )
    write.add_argument(
        "--only",
        action="append",
        metavar="GLOB",
        help="re-write only outputs whose name matches (e.g. 'sdk-java-*')",
    )
    sub.add_parser("deks", help="unwrap, verify and write every DEK and key file")
    derive = sub.add_parser(
        "derive", help="derive fixtures from the written bases into staging"
    )
    derive.add_argument(
        "--only",
        choices=["tamper", "zip"],
        help="derive only this family (default: all)",
    )
    side = sub.add_parser(
        "sidecars", help="copy the synthetic fixtures and write every sidecar"
    )
    side.add_argument(
        "--from",
        dest="src",
        type=Path,
        default=corpus.CORPUS_DIR,
        metavar="DIR",
        help="previous sidecars and synthetic fixtures (default: xtest/corpus)",
    )
    sub.add_parser("install", help="copy the stage into xtest/corpus")
    verdict = sub.add_parser(
        "verdicts", help="write each xtest/corpus sidecar's [sdk] table"
    )
    verdict.add_argument(
        "records",
        nargs="+",
        type=Path,
        metavar="REC.jsonl",
        help="--corpus-record output, one file per platform",
    )
    args = ap.parse_args(argv)
    # Resolved before the chdir, so relative paths mean the caller's.
    src = args.src.resolve() if args.cmd == "sidecars" else None
    records = [p.resolve() for p in args.records] if args.cmd == "verdicts" else []

    os.chdir(runtime.XTEST)
    if args.cmd == "verdicts":
        return verdicts.run_verdicts(records, runtime.scratch_dir(), corpus.CORPUS_DIR)
    if args.cmd == "write":
        return steps.run_write(args.only)
    if args.cmd == "derive":
        scratch = runtime.scratch_dir()
        rc = 0
        if args.only in (None, "tamper"):
            rc |= tamper.run(scratch, corpus.kas_keys())
        if args.only in (None, "zip"):
            rc |= zipcases.run(scratch)
        return rc
    if src is not None:
        return sidecars.run_sidecars(runtime.scratch_dir(), src)
    if args.cmd == "install":
        return sidecars.run_install(runtime.scratch_dir(), corpus.CORPUS_DIR)
    return steps.run_deks()


if __name__ == "__main__":
    sys.exit(main())
