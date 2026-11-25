"""The generator's `write` and `deks` steps.

Output goes to the scratch dir (runtime.scratch_dir()), never to xtest/corpus:
  stage/            sdk-* fixtures, and stage/keys/ for key files; `derive`
                    adds tamper-* (see tamper.py)
  bases/            tamper-base-*.tdf
  plaintexts/       one plaintext per output
  pki/              RS256 signer keys, the x5c test chain, and the forged
                    x5c signer `derive` uses
  manifest.json     {name: {kind, sdk, version, plaintext, plaintext_sha256,
                    key_stem, job}} for every output; later steps read it
"""

import base64
import fnmatch
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import abac
import corpus
import corpus_kas
from corpus_gen import deks, pki, runtime, tamper, variants
from corpus_gen.variants import AssertionSpec, Keys, WriteJob

_KAO_TYPE = {
    "rsa": "wrapped",
    "ec": "ec-wrapped",
    "hpqt": "hybrid-wrapped",
    "mlkem": "mlkem-wrapped",
}


class StepError(Exception):
    pass


@dataclass(frozen=True)
class Planned:
    name: str  # output file name
    kind: str  # "sdk" or "base"
    label: str  # fixture SDK label: go, java, web
    key_stem: str  # key files are keys/<key_stem>.*
    size: int
    job: WriteJob
    out: Path


def plan(keys: Keys, scratch: Path) -> list[Planned]:
    out: list[Planned] = []
    for label, names in variants.WRITERS.items():
        for v in names:
            stem = f"sdk-{label}-{v}"
            out.append(
                Planned(
                    f"{stem}.tdf",
                    "sdk",
                    label,
                    stem,
                    variants.plaintext_size(v),
                    variants.job_for(label, v, keys),
                    scratch / "stage" / f"{stem}.tdf",
                )
            )
    for b, base in variants.TAMPER_BASES.items():
        name = f"tamper-base-{b}.tdf"
        out.append(
            Planned(
                name,
                "base",
                base.sdk,
                tamper.key_stem(b),
                base.size,
                base.job(keys),
                scratch / "bases" / name,
            )
        )
    return out


def _sign(job: WriteJob, stem: str, pki_dir: Path) -> None:
    for a in job.get("assertions", []):
        if a.get("alg") != "RS256" or "key_pem" in a:
            continue
        if "x5c" in a:
            chain = pki.x5c_chain(pki_dir)
            a["key_pem"] = chain.leaf_key
            a["x5c"] = [chain.leaf, chain.intermediate]
        else:
            a["key_pem"] = pki.signer_key(pki_dir, stem)


def prepare(p: Planned, scratch: Path) -> None:
    """Ready one output for its writer: plaintext and signing keys in place, the
    old file and its key files gone, so `deks` must run again before keys exist."""
    pt = scratch / "plaintexts" / f"{p.key_stem}.txt"
    pt.parent.mkdir(parents=True, exist_ok=True)
    pt.write_bytes(variants.plaintext(p.key_stem, p.size))
    p.out.unlink(missing_ok=True)
    deks.remove_key_files(scratch / "stage" / "keys", p.key_stem)
    p.job["out"] = str(p.out)
    p.job["plaintext"] = str(pt)
    _sign(p.job, p.key_stem, scratch / "pki")


def _jws_header(binding: dict[str, Any]) -> dict[str, Any]:
    head = binding["signature"].split(".")[0]
    return json.loads(base64.urlsafe_b64decode(head + "=" * (-len(head) % 4)))


def _assertion_id(a: AssertionSpec) -> str:
    """The manifest id: explicit, else the writers' default."""
    if a["kind"] == "system-metadata":
        return "system-metadata"
    return a.get("id", f"handling-{a.get('alg', '').lower()}")


def _expected_kaos(job: WriteJob, keys: Keys) -> list[tuple[str, str]]:
    prefix = f"{corpus_kas.ATTR_BASE}/"
    kids = [
        corpus_kas.VALUE_KEYS[a.removeprefix(prefix)] for a in job.get("attributes", [])
    ]
    if not kids:
        kids = [k["kid"] for k in job.get("kas", [])]
    return sorted((variants.KAS_URL[keys[k]["kas"]], k) for k in kids)


def _check_sids(p: Planned, sids: list[str], fail: Callable[[str], None]) -> None:
    if len(sids) == 1:
        return
    distinct = set(sids)
    if "" in distinct:
        fail(f"a KAO of {len(sids)} has no split id")
    split = p.job.get("split", [])
    if split and all("sid" in s for s in split):
        want = sorted(s.get("sid", "") for s in split)
        if sorted(sids) != want:
            fail(f"split ids {sids}, job asked for {want}")
        return
    attrs = p.job.get("attributes", [])
    rules = {f"{corpus_kas.ATTR_BASE}/{n}": r for n, r, _ in corpus_kas.ATTRIBUTES}
    if attrs and rules[attrs[0].rsplit("/value/", 1)[0]] == abac.AttributeRule.ANY_OF:
        if len(distinct) != 1:
            fail(f"ANY_OF KAOs should share one split id, got {sids}")
    elif len(distinct) != len(sids):
        fail(f"KAOs should each have their own split id, got {sids}")


def check_written(p: Planned, keys: Keys) -> None:
    """Fail unless the written file has the shape the job asked for."""

    def fail(msg: str) -> None:
        raise StepError(f"{p.name}: {msg}")

    with zipfile.ZipFile(p.out) as z:
        if not {"0.manifest.json", "0.payload"} <= set(z.namelist()):
            fail(f"entries {z.namelist()}")
        m = json.loads(z.read("0.manifest.json"))
    enc = m["encryptionInformation"]
    kaos = enc["keyAccess"]
    got = sorted((k["url"], k.get("kid", "")) for k in kaos)
    want = _expected_kaos(p.job, keys)
    if got != want:
        fail(f"KAOs (url, kid) {got}, expected {want}")
    for k in kaos:
        want_type = _KAO_TYPE[keys[k["kid"]]["alg"].split(":")[0]]
        if k["type"] != want_type:
            fail(f"KAO {k['kid']} type {k['type']}, expected {want_type}")
    _check_sids(p, [k.get("sid") or "" for k in kaos], fail)

    integrity = enc["integrityInformation"]
    sizes = [s for s, _ in deks.segment_sizes(integrity)]
    if sum(sizes) != p.size:
        fail(f"segments hold {sum(sizes)} bytes, plaintext has {p.size}")
    seg = p.job.get("segment_size")
    if seg is not None and (integrity["segmentSizeDefault"] != seg or len(sizes) < 2):
        fail(f"segments {sizes} with default {integrity['segmentSizeDefault']}")
    mime = p.job.get("mime_type")
    if mime is not None and m["payload"].get("mimeType") != mime:
        fail(f"mimeType {m['payload'].get('mimeType')!r}")
    if p.job.get("target_mode") == "4.2.2" and "schemaVersion" in m:
        fail("4.2.2 target but the manifest has schemaVersion")

    asserts = {a["id"]: a for a in m.get("assertions") or []}
    want_ids = {_assertion_id(a) for a in p.job.get("assertions", [])}
    if set(asserts) != want_ids:
        fail(f"assertions {sorted(asserts)}, expected {sorted(want_ids)}")
    for a in p.job.get("assertions", []):
        got = asserts[_assertion_id(a)]
        if a["kind"] == "handling":
            shape = {
                "type": "handling",
                "scope": a.get("scope", got["scope"]),
                "appliesToState": a.get("applies_to_state", got["appliesToState"]),
                "statement": a.get("statement", got["statement"]),
            }
            if {k: got.get(k) for k in shape} != shape:
                fail(f"assertion {got['id']} is not the job's shape {shape}")
        x5c = a.get("x5c")
        if x5c:
            header = _jws_header(got["binding"])
            if len(header.get("x5c", [])) != len(x5c):
                fail(f"JWS header x5c {header.get('x5c')!r}")


def _matches(p: Planned, only: list[str] | None) -> bool:
    if not only:
        return True
    stem = p.name.removesuffix(".tdf")
    return any(fnmatch.fnmatch(p.name, g) or fnmatch.fnmatch(stem, g) for g in only)


def _load_manifest(scratch: Path) -> dict[str, Any]:
    path = scratch / "manifest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _output_path(scratch: Path, out: str) -> Path:
    """A TDF path from writer output or the manifest: under stage/ or bases/."""
    for sub in ("stage", "bases"):
        try:
            return runtime.inside(scratch / sub, out, "output path")
        except runtime.PathEscapeError:
            pass
    raise StepError(f"output path {out!r} is outside {scratch}/stage and /bases")


def _run_writers(
    groups: dict[str, list[Planned]], scratch: Path, env: dict[str, str]
) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Run each SDK's writer once over its jobs, concurrently."""
    procs: dict[str, tuple[subprocess.Popen[str], Path]] = {}
    for sdk, items in groups.items():
        jobs = scratch / f"jobs-{sdk}.json"
        jobs.write_text(json.dumps([p.job for p in items], indent=1))
        log = scratch / f"writer-{sdk}.log"
        with log.open("w") as err:
            procs[sdk] = (
                subprocess.Popen(
                    [*runtime.writer_cmd(sdk), str(jobs)],
                    cwd=runtime.XTEST,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=err,
                    text=True,
                ),
                log,
            )
    written: dict[str, dict[str, str]] = {}
    failed: list[str] = []
    for sdk, (proc, log) in procs.items():
        stdout, _ = proc.communicate()
        for line in stdout.splitlines():
            rec = json.loads(line)
            written[str(_output_path(scratch, rec["out"]))] = rec
        if proc.returncode != 0:
            tail = "\n".join(log.read_text().splitlines()[-20:])
            failed.append(f"{sdk} writer exited {proc.returncode} (log {log}):\n{tail}")
    return written, failed


def run_write(only: list[str] | None) -> int:
    scratch = runtime.scratch_dir()
    keys = corpus.kas_keys()
    todo = [p for p in plan(keys, scratch) if _matches(p, only)]
    if not todo:
        print(f"nothing matches {only}", file=sys.stderr)
        return 2
    manifest = _load_manifest(scratch) if only else {}
    if not only:
        for d in ("stage", "bases", "plaintexts"):
            shutil.rmtree(scratch / d, ignore_errors=True)
    for d in ("stage", "bases", "plaintexts", "pki"):
        (scratch / d).mkdir(parents=True, exist_ok=True)

    env = runtime.load_env()
    runtime.setup_platform()

    groups: dict[str, list[Planned]] = {}
    for p in todo:
        prepare(p, scratch)
        groups.setdefault(variants.WRITER_SDK[p.label], []).append(p)

    written, failed = _run_writers(groups, scratch, env)
    for p in todo:
        manifest.pop(p.name, None)
        rec = written.get(str(p.out))
        if rec is None:
            failed.append(f"{p.name}: not written")
            continue
        try:
            check_written(p, keys)
        except StepError as e:
            failed.append(str(e))
            continue
        except (KeyError, zipfile.BadZipFile) as e:
            failed.append(f"{p.name}: {e!r}")
            continue
        pt = scratch / "plaintexts" / f"{p.key_stem}.txt"
        manifest[p.name] = {
            "kind": p.kind,
            "sdk": rec["sdk"],
            "version": rec["version"],
            "plaintext": str(pt),
            "plaintext_sha256": hashlib.sha256(pt.read_bytes()).hexdigest(),
            "key_stem": p.key_stem,
            "job": p.job,
        }
        print(f"ok   {p.name} ({rec['sdk']} {rec['version']}, {p.size} bytes)")
    with (scratch / "manifest.json").open("w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    for f in failed:
        print(f"FAIL {f}", file=sys.stderr)
    sdk_n = sum(1 for e in manifest.values() if e["kind"] == "sdk")
    base_n = len(manifest) - sdk_n
    print(f"{sdk_n} sdk fixtures, {base_n} tamper bases in {scratch}")
    return 1 if failed else 0


class _Unwrapper:
    """dek unwrap with the corpus private key named by each KAO's kid."""

    def __init__(self, scratch: Path, keys: Keys):
        self.dir = scratch / "dek"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.binary = self.dir / "dek"
        subprocess.run(
            ["go", "-C", "corpus_gen/dek", "build", "-o", str(self.binary), "."],
            cwd=runtime.XTEST,
            check=True,
        )
        self.pems: dict[str, Path] = {}
        for kid, k in keys.items():
            path = self.dir / f"{kid}.pem"
            path.write_text(k["privateKey"])
            path.chmod(0o600)
            self.pems[kid] = path

    def __call__(self, kao: dict[str, Any]) -> bytes:
        kid = kao.get("kid")
        if kid not in self.pems:
            raise deks.DekError(f"KAO kid {kid!r} is not a corpus key")
        kao_file = self.dir / "kao.json"
        kao_file.write_text(json.dumps(kao))
        run = subprocess.run(
            [str(self.binary), "unwrap", "--private", str(self.pems[kid])]
            + ["--kao", str(kao_file)],
            capture_output=True,
            text=True,
        )
        if run.returncode != 0:
            raise deks.DekError(f"dek unwrap ({kid}): {run.stderr.strip()}")
        return bytes.fromhex(run.stdout.strip())


def _key_files(
    entry: dict[str, Any], unwrap: _Unwrapper, scratch: Path
) -> dict[str, str]:
    """Key file name -> contents for one output, after proving the DEK."""
    pt_path = runtime.inside(scratch / "plaintexts", entry["plaintext"], "plaintext")
    plaintext = pt_path.read_bytes()
    if hashlib.sha256(plaintext).hexdigest() != entry["plaintext_sha256"]:
        raise deks.DekError("plaintext changed since write")
    with zipfile.ZipFile(_output_path(scratch, entry["job"]["out"])) as z:
        manifest = json.loads(z.read("0.manifest.json"))
        payload = z.read("0.payload")
    enc = manifest["encryptionInformation"]
    kaos = enc["keyAccess"]
    pairs: list[tuple[str, bytes]] = []
    for kao in kaos:
        share = unwrap(kao)
        deks.check_binding(share, kao, enc["policy"])
        pairs.append((kao.get("sid") or "", share))
    dek, shares = deks.combine(pairs)
    deks.verify_dek(dek, manifest, payload, plaintext)

    stem = entry["key_stem"]
    files = {f"{stem}.dek": dek.hex() + "\n"}
    files |= deks.share_files(stem, shares, len(kaos))
    for a in entry["job"].get("assertions", []):
        if a.get("alg") == "RS256":
            suffix = "leaf.pub.pem" if a.get("x5c") else "pub.pem"
            files[f"{stem}.{suffix}"] = pki.public_pem(a["key_pem"])
    return files


def run_deks() -> int:
    scratch = runtime.scratch_dir()
    entries = _load_manifest(scratch)
    if not entries:
        print(f"no {scratch / 'manifest.json'}; run `write` first", file=sys.stderr)
        return 2
    keys_dir = scratch / "stage" / "keys"
    shutil.rmtree(keys_dir, ignore_errors=True)
    keys_dir.mkdir(parents=True)
    unwrap = _Unwrapper(scratch, corpus.kas_keys())

    failures = 0
    for name, entry in sorted(entries.items()):
        try:
            files = _key_files(entry, unwrap, scratch)
        except (
            deks.DekError,
            StepError,
            OSError,
            KeyError,
            ValueError,
            zipfile.BadZipFile,
        ) as e:
            failures += 1
            print(f"FAIL {name}: {e}", file=sys.stderr)
            continue
        for fname, text in files.items():
            dest = runtime.inside(keys_dir, fname, "key file")
            if dest.exists():
                raise StepError(f"{fname} written twice")
            dest.write_text(text)
        print(f"ok   {name}: DEK verified; {', '.join(files)}")
    print(f"{len(entries) - failures}/{len(entries)} DEKs verified into {keys_dir}")
    return 1 if failures else 0
