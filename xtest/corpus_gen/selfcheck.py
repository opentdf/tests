"""Smoke-test a corpus writer: write three TDFs to the corpus keys on km1,
decrypt each with the same SDK's cli.sh and compare the plaintext.

Run from xtest/ with the platform and km1/km2 up and OT_ROOT_KEY set:
    uv run python -m corpus_gen.selfcheck --sdk go
"""

import argparse
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import corpus
from corpus_gen.runtime import (
    CLI,
    KM1,
    XTEST,
    load_env,
    scratch_dir,
    setup_platform,
    writer_cmd,
)

KID = "corpus-r2048"
# SDKs that name their own split ids (the Java SDK writes random UUIDs).
OWN_SPLIT_IDS = {"java"}


def _jobs(scratch: Path, sdk: str) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    plain = {
        "basic": b"corpus selfcheck basic\n",
        "multi-segment": bytes(i % 251 for i in range(40 * 1024)),
        "split-two-kao": b"corpus selfcheck split\n",
    }
    key = corpus.kas_keys()[KID]
    kas = [{"url": KM1, "kid": KID, "alg": key["alg"]}]
    jobs: list[dict[str, Any]] = []
    for name, data in plain.items():
        pt = scratch / f"{name}.txt"
        pt.write_bytes(data)
        job: dict[str, Any] = {
            "out": str(scratch / f"{name}.tdf"),
            "plaintext": str(pt),
            "kas": kas,
        }
        if name == "multi-segment":
            job["segment_size"] = 16384
        if name == "split-two-kao":
            job["kas"] = kas * 2
            job["split"] = [{"kas": 0, "sid": "s-0"}, {"kas": 1, "sid": "s-1"}]
            if sdk in OWN_SPLIT_IDS:
                job["split"] = [{"kas": 0}, {"kas": 1}]
        jobs.append(job)
    return jobs, plain


def _check_manifest(name: str, tdf: Path) -> None:
    with zipfile.ZipFile(tdf) as z:
        manifest = json.loads(z.read("0.manifest.json"))
    enc = manifest["encryptionInformation"]
    kaos = enc["keyAccess"]
    for kao in kaos:
        assert kao["url"] == KM1, f"{name}: KAO url {kao['url']}"
        assert kao.get("kid") == KID, f"{name}: KAO kid {kao.get('kid')}"
    if name == "split-two-kao":
        sids = {kao.get("sid") for kao in kaos}
        assert len(kaos) == 2 and len(sids) == 2, f"{name}: split ids {sids}"
    if name == "multi-segment":
        segs = enc["integrityInformation"]["segments"]
        assert len(segs) > 1, f"{name}: only {len(segs)} segment(s)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sdk", required=True, choices=sorted(CLI))
    args = ap.parse_args()
    os.chdir(XTEST)
    env = load_env()

    scratch = scratch_dir() / "selfcheck"
    scratch.mkdir(parents=True, exist_ok=True)

    setup_platform(attributes=False)
    jobs, plain = _jobs(scratch, args.sdk)
    jobs_file = scratch / f"jobs-{args.sdk}.json"
    jobs_file.write_text(json.dumps(jobs))

    run = subprocess.run(
        [*writer_cmd(args.sdk), str(jobs_file)], env=env, capture_output=True, text=True
    )
    sys.stderr.write(run.stderr)
    if run.returncode != 0:
        print(f"FAIL: {args.sdk} writer exited {run.returncode}", file=sys.stderr)
        return 1
    print(run.stdout, end="")

    failures = 0
    for job in jobs:
        name = Path(job["out"]).stem
        tdf, rt = Path(job["out"]), scratch / f"{name}.{args.sdk}.out"
        try:
            dec = subprocess.run(
                [CLI[args.sdk], "decrypt", str(tdf), str(rt), "ztdf"],
                env=env,
                capture_output=True,
                text=True,
            )
            assert dec.returncode == 0, f"decrypt failed: {dec.stderr[-500:]}"
            assert rt.read_bytes() == plain[name], "plaintext mismatch"
            _check_manifest(name, tdf)
            print(f"ok   {args.sdk} {name}")
        except (AssertionError, OSError, KeyError, ValueError) as e:
            failures += 1
            print(f"FAIL {args.sdk} {name}: {e}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
