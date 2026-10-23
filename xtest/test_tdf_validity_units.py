"""Offline tests for the TDF validity suite's harness (DSPX-5349).

No platform and no SDK build. ``test_tdf_validity.py`` can only be as right
as the corpus it feeds every SDK, the parser that turns a CLI run into a
verdict, and the baseline it holds that verdict to -- so each is checked
here, on every PR, rather than discovered wrong in a nightly.

The shim tests at the bottom run the real ``sdk/*/cli.sh`` scripts against
stand-in CLIs, which is the closest this repo can get to the per-SDK
``validate`` commands before they release.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import time
import zipfile
import zlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import jsonschema
import pytest

import tdfs
import tdfvalidity as tv
import tdfvalidity_corpus as corpus
import tdfvalidity_fixtures as gofix
import zipinspect

XTEST = Path(__file__).parent
CASES = corpus.corpus()
BY_ID = corpus.by_id(CASES)


def _zip(data: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(data))


def _inspect(tmp_path: Path, data: bytes) -> zipinspect.CentralDirectory:
    p = tmp_path / "c.zip"
    p.write_bytes(data)
    return zipinspect.central_directory(p)


# --- the corpus --------------------------------------------------------------


class TestCorpusShape:
    def test_is_deterministic(self):
        again = corpus.corpus()
        assert [c.id for c in again] == [c.id for c in CASES]
        assert corpus.digest(again) == corpus.digest(CASES)

    def test_ids_and_filenames_are_unique(self):
        assert len({c.id for c in CASES}) == len(CASES)
        assert len({c.filename for c in CASES}) == len(CASES)

    def test_every_group_is_present(self):
        groups = {c.group for c in CASES}
        assert groups >= {
            "control",
            "archive",
            "truncated",
            "zip",
            "profile",
            "name",
            "json",
            "manifest",
            "schema",
            "writer",
            "golden",
            "scope",
        }

    def test_undecided_cases_name_their_decision(self):
        for c in CASES:
            if c.expect == "undecided":
                assert c.ticket, c.id

    def test_invalid_cases_say_where_they_should_fail(self):
        """Without a layer, no SDK's reason can be checked."""
        missing = [c.id for c in CASES if c.expect == "invalid" and c.layer is None]
        assert not missing

    def test_bad_ids_are_refused(self):
        with pytest.raises(ValueError, match="not <group>/<slug>"):
            corpus.Case("no-slash", b"", "valid", "x")
        with pytest.raises(ValueError, match="decision ticket"):
            corpus.Case("a/b", b"", "undecided", "x")

    def test_write_round_trips(self, tmp_path: Path):
        paths = corpus.write(CASES[:5], tmp_path)
        for c in CASES[:5]:
            assert paths[c.id].read_bytes() == c.data
        mtime = paths[CASES[0].id].stat().st_mtime_ns
        time.sleep(0.01)
        corpus.write(CASES[:5], tmp_path)
        assert paths[CASES[0].id].stat().st_mtime_ns == mtime, (
            "rewrote an unchanged file"
        )


class TestZipBuilder:
    """The builder's archives, read back by ``zipfile`` and ``zipinspect``."""

    def test_control_reads_back(self):
        z = _zip(BY_ID["control/go-shaped"].data)
        assert z.namelist() == [corpus.PAYLOAD, corpus.MANIFEST]
        assert z.read(corpus.PAYLOAD) == corpus.PAYLOAD_BYTES
        assert json.loads(z.read(corpus.MANIFEST)) == corpus.GO_MANIFEST
        assert z.testzip() is None

    def test_data_descriptor_reads_back(self):
        z = _zip(BY_ID["archive/data-descriptor"].data)
        assert all(i.flag_bits & 0x08 for i in z.infolist())
        assert z.read(corpus.PAYLOAD) == corpus.PAYLOAD_BYTES
        assert z.testzip() is None

    def test_zip64_is_really_zip64(self, tmp_path: Path):
        data = BY_ID["archive/zip64"].data
        assert _zip(data).read(corpus.PAYLOAD) == corpus.PAYLOAD_BYTES
        cd = _inspect(tmp_path, data)
        assert all(e.has_zip64_extra for e in cd.entries)
        assert all(
            e.uses_zip64_for_offset and e.uses_zip64_for_sizes for e in cd.entries
        )
        assert [e.local_header_offset for e in cd.entries][0] == 0

    def test_comment(self):
        assert _zip(BY_ID["archive/comment"].data).comment == b"hello"
        assert len(_zip(BY_ID["archive/comment-max"].data).comment) == 0xFFFF

    def test_deflated_entries_are_really_deflated(self):
        z = _zip(BY_ID["archive/deflated-payload"].data)
        assert z.getinfo(corpus.PAYLOAD).compress_type == zipfile.ZIP_DEFLATED
        assert z.read(corpus.PAYLOAD) == corpus.PAYLOAD_BYTES
        z = _zip(BY_ID["archive/deflated-manifest"].data)
        assert json.loads(z.read(corpus.MANIFEST)) == corpus.GO_MANIFEST

    def test_method_8_on_stored_bytes_does_not_inflate(self):
        z = _zip(BY_ID["archive/method-8-on-stored-bytes"].data)
        with pytest.raises((zipfile.BadZipFile, zlib.error)):
            z.read(corpus.PAYLOAD)

    def test_size_mismatch_is_declared(self):
        info = _zip(BY_ID["archive/payload-size-mismatch"].data).getinfo(corpus.PAYLOAD)
        assert info.file_size == info.compress_size + 1

    def test_cd_size_lie_is_past_eof(self, tmp_path: Path):
        with pytest.raises(zipinspect.MalformedZipError, match="past the end"):
            _inspect(tmp_path, BY_ID["archive/cd-size-0xfffffff0"].data)

    def test_overrides_only_change_the_trailer(self):
        base = corpus.build_zip([corpus.Entry("a", b"x")])
        lied = corpus.build_zip([corpus.Entry("a", b"x")], entry_count=9)
        cd = dict(base.boundaries)["cd"]
        assert lied.data[:cd] == base.data[:cd]
        assert lied.data != base.data

    def test_boundaries_are_in_file_order(self):
        built = corpus.build_zip(
            [corpus.Entry("a", b"x", zip64=True, data_descriptor=True)],
            zip64_eocd=True,
        )
        offsets = [at for _, at in built.boundaries]
        assert offsets == sorted(offsets)
        labels = [label for label, _ in built.boundaries]
        assert labels == ["lfh0", "data0", "dd0", "cd", "eocd64", "locator", "eocd"]


class TestCaseContents:
    def test_truncations_are_distinct_strict_prefixes(self):
        cases = [c for c in CASES if c.group == "truncated"]
        assert len(cases) >= 20
        for shape in ("zip32", "zip64"):
            mine = [c for c in cases if c.id.startswith(f"truncated/{shape}-")]
            full = max(mine, key=lambda c: len(c.data))
            whole = len(full.data) + 1  # "last-byte" drops exactly one
            assert all(full.data.startswith(c.data) for c in mine)
            assert len({len(c.data) for c in mine}) == len(mine)
            assert all(0 < len(c.data) < whole for c in mine)

    def test_malformed_archives_do_not_parse(self, tmp_path: Path):
        for case_id in (
            "zip/empty",
            "zip/random",
            "zip/text",
            "zip/cd-offset-past-eof",
            "zip/entry-count-overstated",
            "zip/bad-cd-signature",
            "zip/zip64-locator-past-eof",
            "zip/zip64-eocd-bad-signature",
        ):
            with pytest.raises(zipinspect.MalformedZipError):
                _inspect(tmp_path, BY_ID[case_id].data)

    def test_local_header_lies_fail_on_read(self):
        for case_id in (
            "zip/local-header-past-eof",
            "zip/local-header-in-cd",
            "zip/bad-local-header-signature",
        ):
            z = _zip(BY_ID[case_id].data)
            with pytest.raises((zipfile.BadZipFile, ValueError, OSError)):
                z.read(corpus.MANIFEST)

    def test_eocd_only_is_an_empty_archive(self):
        assert _zip(BY_ID["zip/eocd-only"].data).namelist() == []

    def test_duplicates_really_are_duplicated(self):
        names = _zip(BY_ID["profile/duplicate-legacy-name-valid-last"].data).namelist()
        assert names.count(corpus.MANIFEST) == 2
        names = _zip(BY_ID["profile/duplicate-pairs"].data).namelist()
        assert names.count(corpus.MANIFEST) == names.count(corpus.PAYLOAD) == 2

    def test_name_cases_carry_the_names_they_claim(self):
        names = _zip(BY_ID["name/spec-invalid-legacy-valid"].data).namelist()
        assert {corpus.MANIFEST, corpus.SPEC_MANIFEST} <= set(names)
        z = _zip(BY_ID["name/spec-name"].data)
        assert corpus.MANIFEST not in z.namelist()
        assert corpus.SPEC_MANIFEST in z.namelist()

    def test_bom_is_a_real_bom(self):
        z = _zip(BY_ID["json/bom-legacy-name"].data)
        assert z.read(corpus.MANIFEST).startswith(b"\xef\xbb\xbf{")

    def test_nesting_depths(self):
        for depth in (32, 1000, 20000):
            raw = _zip(BY_ID[f"json/nesting-{depth}"].data).read(corpus.MANIFEST)
            assert raw.count(b"[") == depth
        raw = _zip(BY_ID["json/nesting-32"].data).read(corpus.MANIFEST)
        assert json.loads(raw)["payload"] == corpus.MINIMAL["payload"]

    def test_trailing_cases_start_with_a_whole_manifest(self):
        good = corpus.dumps(corpus.MINIMAL).encode()
        for case_id in ("json/trailing-garbage", "json/trailing-object"):
            raw = _zip(BY_ID[case_id].data).read(corpus.MANIFEST)
            assert raw.startswith(good) and raw != good

    def test_large_manifest_is_past_the_old_go_cap(self):
        info = _zip(BY_ID["json/large-11mib"].data).getinfo(corpus.MANIFEST)
        assert info.file_size > 10 * 1024 * 1024

    def test_scope_cases_keep_the_manifest_intact(self):
        for c in CASES:
            if c.group != "scope":
                continue
            z = _zip(c.data)
            if c.id == "scope/manifest-crc-mismatch":
                with pytest.raises(zipfile.BadZipFile, match="CRC"):
                    z.read(corpus.MANIFEST)
                continue
            assert json.loads(z.read(corpus.MANIFEST)) == corpus.GO_MANIFEST, c.id

    def test_golden_cases_are_the_files(self):
        for name in corpus.GOLDEN_FILES:
            case_id = f"golden/{corpus._slug(name.removesuffix('.tdf'))}"
            assert BY_ID[case_id].data == (XTEST / "golden" / name).read_bytes()


class TestPinnedInputs:
    """Inputs copied from elsewhere must stay byte-identical to their source."""

    def test_go_fixtures(self):
        digests = {
            name: hashlib.sha256(getattr(gofix, name)).hexdigest()[:16]
            for name in (
                "GO_STANDARD_TDF",
                "GO_SPEC_MANIFEST_NAME_TDF",
                "GO_BAD_STANDARD_TDF",
                "GO_MISSING_PAYLOAD_TYPE_TDF",
            )
        }
        assert digests == {
            "GO_STANDARD_TDF": "99ee59fe5044634d",
            "GO_SPEC_MANIFEST_NAME_TDF": "c45ff000ecbbb34f",
            "GO_BAD_STANDARD_TDF": "b5cb80c111373de7",
            "GO_MISSING_PAYLOAD_TYPE_TDF": "8121d3942119d0b1",
        }

    def test_lax_schema_is_go_v0_35_0(self):
        """platform/sdk v0.35.0 schema/manifest-lax.schema.json, verbatim.

        web-sdk#1104 vendors the same schema. If Go changes it (DSPX-4388 adds
        mlkem-wrapped), re-vendor, update this digest, and expect the schema/
        cases and the baseline to move with it.
        """
        digest = hashlib.sha256(corpus.LAX_SCHEMA_PATH.read_bytes()).hexdigest()
        assert digest == (
            "5e361720f005b23211a37d9e89c2c7ef51bc1b7df3353b82c2a568c3ed33f87d"
        )


# --- agreed answers vs. the lax schema ---------------------------------------

LAX = corpus.load_lax_schema()

#: Cases whose agreed answer is not what the lax schema says, and why.
SCHEMA_DISAGREES = {
    "writer/go-mlkem-wrapped": "DSPX-4388: the schema omits mlkem-wrapped",
    "writer/js-mlkem-wrapped": "DSPX-4388: the schema omits mlkem-wrapped",
}


def _manifest_cases() -> Iterator[tuple[corpus.Case, Any]]:
    for c in CASES:
        if c.manifest_text is not None:
            yield c, json.loads(c.manifest_text)


class TestAgreedAnswers:
    def test_match_the_lax_schema(self):
        """Every hand-assigned answer is what an independent validator says.

        ``jsonschema`` shares no code with Go's gojsonschema or web-sdk's
        @cfworker/json-schema, so agreement here means the corpus's answers
        come from the schema, not from either SDK's reading of it.
        """
        validator = jsonschema.Draft202012Validator(LAX)
        wrong = []
        for c, manifest in _manifest_cases():
            if c.expect not in ("valid", "invalid") or c.id in SCHEMA_DISAGREES:
                continue
            got = "valid" if validator.is_valid(manifest) else "invalid"
            if got != c.expect:
                wrong.append(f"{c.id}: agreed {c.expect}, lax schema says {got}")
        assert not wrong

    def test_known_disagreements_still_disagree(self):
        validator = jsonschema.Draft202012Validator(LAX)
        for case_id in SCHEMA_DISAGREES:
            manifest = json.loads(BY_ID[case_id].manifest_text or "null")
            assert not validator.is_valid(manifest), (
                f"{case_id} now passes the lax schema; drop it from SCHEMA_DISAGREES"
            )

    def test_web_sdk_cases_are_all_ported(self):
        cases = [c for c in CASES if c.group == "manifest"]
        assert len(cases) == 42
        assert sum(c.expect == "valid" for c in cases) == 16

    def test_archive_manifests_pass_the_strict_schema_too(self):
        """So no archive-layer case hinges on which schema a reader uses."""
        strict = json.loads((XTEST / "manifest.schema.json").read_text())
        validator = jsonschema.Draft202012Validator(strict)
        for manifest in (corpus.GO_MANIFEST, corpus.JS_MANIFEST):
            assert validator.is_valid(manifest)


def _mutants(node: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Yield ``(where, schema)`` for every single-keyword mutant of ``node``.

    A mutant drops one keyword, one member of a list-valued keyword (a type
    union, an enum, a required list, a oneOf), or one property's subschema.
    Annotations (description, title, ids) are not keywords that change a
    verdict, so they are left alone.
    """
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if key in ("description", "title", "$schema", "$id"):
            continue
        dropped = {k: v for k, v in node.items() if k != key}
        yield f"{path}/{key}", dropped
        if isinstance(value, list):
            for i, member in enumerate(value):
                rest = [m for j, m in enumerate(value) if j != i]
                yield (
                    f"{path}/{key}/{member if not isinstance(member, dict) else i}",
                    {
                        **node,
                        key: rest,
                    },
                )
        if key == "properties" and isinstance(value, dict):
            for name in value:
                without = {k: v for k, v in value.items() if k != name}
                yield f"{path}/properties/{name}", {**node, "properties": without}
    for name, sub in node.get("properties", {}).items():
        for where, mutant in _mutants(sub, f"{path}/{name}"):
            yield where, {**node, "properties": {**node["properties"], name: mutant}}
    if isinstance(node.get("items"), dict):
        for where, mutant in _mutants(node["items"], f"{path}/items"):
            yield where, {**node, "items": mutant}
    for i, branch in enumerate(node.get("oneOf", [])):
        for where, mutant in _mutants(branch, f"{path}/oneOf{i}"):
            branches = copy.copy(node["oneOf"])
            branches[i] = mutant
            yield where, {**node, "oneOf": branches}


#: Mutants no input can tell from the real schema, and why.
EQUIVALENT_MUTANTS = {
    # JSON Schema ignores ``required`` on a non-object; this one sits beside
    # keyAccess's ``items`` rather than inside it. That is why web-sdk#1104's
    # "partial key access item" ``[{}]`` is valid.
    "/encryptionInformation/keyAccess/required",
    "/encryptionInformation/keyAccess/required/type",
    "/encryptionInformation/keyAccess/required/url",
    "/encryptionInformation/keyAccess/required/protocol",
    "/encryptionInformation/keyAccess/required/wrappedKey",
    "/encryptionInformation/keyAccess/required/sid",
    "/encryptionInformation/keyAccess/required/kid",
    "/encryptionInformation/keyAccess/required/policyBinding",
    # An all-string enum already implies ``type: string``.
    "/encryptionInformation/keyAccess/items/type/type",
    "/encryptionInformation/keyAccess/items/protocol/type",
    # payload.protocol's subschema is a bare description.
    "/payload/properties/protocol",
}


class TestMutationAnalysis:
    """The corpus decides every keyword of the lax schema.

    A mutation analysis of web-sdk#1104's 42 cases found 70 of 110 single-keyword
    mutants survived -- including dropping ``wrapped`` from the key access type
    enum -- so a validator could lose any of those checks and every SDK's suite
    would stay green. Here each mutant must change at least one case's verdict.
    """

    def test_every_mutant_is_killed(self):
        manifests = [m for _, m in _manifest_cases()]
        original = jsonschema.Draft202012Validator(LAX)
        baseline = [original.is_valid(m) for m in manifests]
        survivors = []
        total = 0
        for where, mutant in _mutants(LAX):
            total += 1
            if where in EQUIVALENT_MUTANTS:
                continue
            v = jsonschema.Draft202012Validator(mutant)
            if [v.is_valid(m) for m in manifests] == baseline:
                survivors.append(where)
        assert total > 100
        assert not survivors, f"{len(survivors)} of {total} mutants survive"

    def test_equivalent_mutants_really_survive(self):
        """An entry here that some case now kills is stale; remove it."""
        manifests = [m for _, m in _manifest_cases()]
        original = jsonschema.Draft202012Validator(LAX)
        baseline = [original.is_valid(m) for m in manifests]
        found = dict(_mutants(LAX))
        for where in EQUIVALENT_MUTANTS:
            v = jsonschema.Draft202012Validator(found[where])
            assert [v.is_valid(m) for m in manifests] == baseline, where

    def test_schema_cases_change_one_thing(self):
        """Each schema/ case differs from the full manifest at a single path."""

        def diff(a: Any, b: Any, path: str = "") -> list[str]:
            if isinstance(a, dict) and isinstance(b, dict):
                out = []
                for k in a.keys() | b.keys():
                    if k not in a or k not in b:
                        out.append(f"{path}/{k}")
                    else:
                        out += diff(a[k], b[k], f"{path}/{k}")
                return out
            if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
                return [
                    d
                    for i, (x, y) in enumerate(zip(a, b, strict=True))
                    for d in diff(x, y, f"{path}/{i}")
                ]
            return [] if a == b and type(a) is type(b) else [path]

        for c, manifest in _manifest_cases():
            if c.group == "schema" and c.id != "schema/full":
                assert len(diff(corpus.FULL_MANIFEST, manifest)) == 1, c.id


# --- the CLI contract ---------------------------------------------------------


class TestParseOutput:
    def test_valid(self):
        r = tv.parse_output(0, b'{"valid":true}\n')
        assert (r.outcome, r.reason, r.returncode) == ("valid", "", 0)

    def test_invalid_with_reason(self):
        r = tv.parse_output(3, b'{"valid":false,"reason":"zip: bad"}\n')
        assert (r.outcome, r.reason) == ("invalid", "zip: bad")

    def test_invalid_without_reason(self):
        assert tv.parse_output(3, b'{"valid":false}').outcome == "invalid"

    @pytest.mark.parametrize("code", [1, 2, 4, 127])
    def test_other_exits_are_errors(self, code: int):
        r = tv.parse_output(code, b"", b"boom\n")
        assert r.outcome == "error"
        assert f"exit {code}" in r.reason
        assert r.stderr == "boom"

    def test_exit_1_with_invalid_json_is_still_an_error(self):
        """The whole reason the contract does not use 1 for invalid."""
        assert tv.parse_output(1, b'{"valid":false}').outcome == "error"

    def test_signal(self):
        r = tv.parse_output(-9, b"")
        assert (r.outcome, r.reason) == ("error", "killed by SIGKILL")

    def test_timeout(self):
        r = tv.parse_output(None, b"", timed_out=True, timeout=5)
        assert (r.outcome, r.returncode) == ("error", None)
        assert "timed out after 5" in r.reason

    @pytest.mark.parametrize(
        ("code", "stdout", "why"),
        [
            (0, b'{"valid":false}', "contradicts"),
            (3, b'{"valid":true}', "contradicts"),
            (0, b"", "0 lines"),
            (0, b'log line\n{"valid":true}', "2 lines"),
            (0, b"valid", "not JSON"),
            (0, b"[true]", 'no boolean "valid"'),
            (0, b'{"valid":"true"}', 'no boolean "valid"'),
            (3, b'{"valid":false,"reason":7}', "not a string"),
        ],
    )
    def test_contract_violations_are_errors(self, code: int, stdout: bytes, why: str):
        r = tv.parse_output(code, stdout)
        assert r.outcome == "error"
        assert why in r.reason

    def test_long_reasons_are_trimmed(self):
        long = "x" * 5000
        r = tv.parse_output(
            3, json.dumps({"valid": False, "reason": "zip: " + long}).encode()
        )
        assert r.outcome == "invalid" and len(r.reason) < 500
        assert r.reason.startswith("zip: "), "the start says which layer rejected it"


class TestRunBounded:
    def test_passes_through_exit_and_output(self):
        run = tdfs.run_bounded(
            ["sh", "-c", "echo '{\"valid\":false}'; echo err >&2; exit 3"], timeout=10
        )
        assert (run.returncode, run.timed_out) == (3, False)
        assert run.stdout == b'{"valid":false}\n' and run.stderr == b"err\n"

    def test_timeout_kills_the_whole_group(self, tmp_path: Path):
        pidfile = tmp_path / "child.pid"
        start = time.monotonic()
        run = tdfs.run_bounded(
            ["sh", "-c", f"sleep 30 & echo $! > {pidfile}; wait"], timeout=0.5
        )
        assert run.timed_out and run.returncode is None
        assert time.monotonic() - start < 10
        child = int(pidfile.read_text())
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            pytest.fail(f"grandchild {child} outlived the timeout")


def _fake_sdk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: str) -> tdfs.SDK:
    dist = tmp_path / "sdk" / "go" / "dist" / "fake"
    dist.mkdir(parents=True)
    cli = dist / "cli.sh"
    cli.write_text("#!/usr/bin/env bash\n" + script)
    cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
    monkeypatch.chdir(tmp_path)
    return tdfs.SDK("go", "fake")


class TestSdkValidate:
    def test_invalid(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        sdk = _fake_sdk(
            tmp_path,
            monkeypatch,
            '[ "$1" = validate ] || exit 9\n'
            'echo "{\\"valid\\":false,\\"reason\\":\\"got $2\\"}"; exit 3\n',
        )
        r = sdk.validate(Path("x.tdf"))
        assert (r.outcome, r.reason) == ("invalid", "got x.tdf")

    def test_hang_is_an_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        sdk = _fake_sdk(tmp_path, monkeypatch, "sleep 30\n")
        r = sdk.validate(Path("x.tdf"), timeout=0.3)
        assert r.outcome == "error" and "timed out" in r.reason


# --- the baseline --------------------------------------------------------------

SPECS: list[tv.Spec] = [*CASES, *corpus.ROUND_TRIPS]


def _baseline(cells: dict[str, Any], **sdks: dict[str, Any]) -> tv.Baseline:
    return tv.parse_baseline(
        {
            "format": 1,
            "sdks": sdks or {"go": {"status": "seeded"}, "java": {"status": "pending"}},
            "cells": cells,
        }
    )


class TestCheckedInBaseline:
    def test_parses(self):
        tv.load_baseline()

    def test_has_no_problems(self):
        assert tv.problems(tv.load_baseline(), SPECS) == []

    def test_describes_every_sdk(self):
        assert set(tv.load_baseline().sdks) == set(tdfs.sdk_type.__args__)

    def test_every_sdk_is_seeded_from_its_cli_ticket(self):
        """Each SDK's answers came from the code behind its validate command."""
        sdks = tv.load_baseline().sdks
        assert {name: sb.status for name, sb in sdks.items()} == {
            "go": "seeded",
            "java": "seeded",
            "js": "seeded",
        }
        for name, ticket in (
            ("go", "DSPX-5350"),
            ("js", "DSPX-5351"),
            ("java", "DSPX-5352"),
        ):
            assert ticket in sdks[name].source, name

    def test_every_divergence_ticket_is_one_we_know(self):
        """A typo'd key would make a divergence look explained."""
        known = {
            "DSPX-4388",
            "DSPX-5103",
            "DSPX-4924",
            "DSPX-5353",
            "DSPX-5354",
            "DSPX-5355",
            "DSPX-5356",
            "DSPX-5357",
        }
        b = tv.load_baseline()
        used = {c.ticket for row in b.cells.values() for c in row.values() if c.ticket}
        used |= {s.ticket for s in SPECS if s.ticket}
        assert used <= known

    def test_pins_the_epic_divergence_table(self):
        """DSPX-5348's table, verified against Go v0.35.0 and web-sdk#1104."""
        b = tv.load_baseline()

        def outcome(case_id: str, sdk: str) -> str:
            spec = BY_ID[case_id]
            return b.expected(spec, sdk).outcome

        table = {
            "archive/comment": ("invalid", "valid"),
            "json/nesting-20000": ("invalid", "valid"),
            "json/trailing-garbage": ("valid", "invalid"),
            "json/trailing-object": ("valid", "invalid"),
            "archive/deflated-payload": ("valid", "invalid"),
            "archive/method-8-on-stored-bytes": ("valid", "invalid"),
            "archive/payload-size-mismatch": ("valid", "invalid"),
            "archive/cd-size-0xfffffff0": ("valid", "invalid"),
            "writer/go-mlkem-wrapped": ("invalid", "invalid"),
        }
        for case_id, (go, js) in table.items():
            assert (outcome(case_id, "go"), outcome(case_id, "js")) == (go, js), case_id

    def test_mlkem_round_trip_is_a_known_divergence(self):
        b = tv.load_baseline()
        spec = next(s for s in corpus.ROUND_TRIPS if s.id == "roundtrip/mlkem-768")
        for sdk in ("go", "java", "js"):
            cell = b.expected(spec, sdk)
            assert (cell.outcome, cell.ticket) == ("invalid", "DSPX-4388")

    def test_round_trip_features_are_real(self):
        for s in corpus.ROUND_TRIPS:
            assert set(s.features) <= tdfs.ALL_FEATURES, s.id


class TestBaselineParsing:
    @pytest.mark.parametrize(
        ("cell", "match"),
        [
            ("maybe", "outcome"),
            ({"outcome": "valid", "ticket": "dspx 1"}, "tracker key"),
            ({"outcome": "valid", "colour": "red"}, "unknown cell keys"),
            ({"outcome": "invalid", "layer": "payload"}, "layer"),
            (7, "string or an object"),
        ],
    )
    def test_bad_cells(self, cell: object, match: str):
        with pytest.raises(ValueError, match=match):
            _baseline({"a/b": {"go": cell}})

    def test_bad_sdk_entries(self):
        with pytest.raises(ValueError, match="status"):
            _baseline({}, go={"status": "maybe"})
        with pytest.raises(ValueError, match="unknown layer"):
            _baseline({}, go={"status": "seeded", "reason_patterns": {"x": "y"}})
        with pytest.raises(Exception, match="unterminated|missing"):
            _baseline({}, go={"status": "seeded", "reason_patterns": {"archive": "("}})

    def test_bad_format(self):
        with pytest.raises(ValueError, match="format"):
            tv.parse_baseline({"format": 2})

    def test_dump_round_trips(self):
        b = tv.load_baseline()
        assert tv.parse_baseline(json.loads(tv.dump_baseline(b))) == b

    def test_checked_in_file_is_in_canonical_form(self):
        """So a refresh diffs only the cells it changed."""
        raw = tv.BASELINE_PATH.read_text(encoding="utf-8")
        doc = json.loads(raw)
        header = {k: v for k, v in doc.items() if k == "about"}
        assert tv.dump_baseline(tv.parse_baseline(doc), header) == raw


class TestExpected:
    spec = corpus.Case("a/b", b"", "invalid", "x", layer="archive")
    open_spec = corpus.Case("a/c", b"", "undecided", "x", ticket="DSPX-1")

    def test_seeded_sdk_without_a_cell_gets_the_agreed_answer(self):
        assert _baseline({}).expected(self.spec, "go") == tv.Cell("invalid")

    def test_pending_or_unknown_sdk_is_pending(self):
        assert _baseline({}).expected(self.spec, "java").outcome == "pending"
        assert _baseline({}).expected(self.spec, "rust").outcome == "pending"

    def test_undecided_without_a_cell_is_pending(self):
        assert _baseline({}).expected(self.open_spec, "go").outcome == "pending"

    def test_recorded_cell_wins_and_writer_cells_win_over_it(self):
        b = _baseline(
            {
                "a/b": {
                    "go": {"outcome": "valid", "ticket": "DSPX-2"},
                    "go:java": {"outcome": "error", "ticket": "DSPX-3"},
                }
            }
        )
        assert b.expected(self.spec, "go").ticket == "DSPX-2"
        assert b.expected(self.spec, "go", "js").ticket == "DSPX-2"
        assert b.expected(self.spec, "go", "java").ticket == "DSPX-3"


class TestProblems:
    specs: list[tv.Spec] = [
        corpus.Case("a/agreed", b"", "valid", "x"),
        corpus.Case("a/open", b"", "undecided", "x", ticket="DSPX-1"),
        corpus.Case("a/pin", b"", "unspecified", "x"),
    ]
    complete = {"a/open": {"go": "valid"}, "a/pin": {"go": "invalid"}}

    def test_complete_baseline_is_clean(self):
        assert tv.problems(_baseline(self.complete), self.specs) == []

    def test_divergence_needs_a_ticket(self):
        b = _baseline({**self.complete, "a/agreed": {"go": "invalid"}})
        assert any("without a ticket" in p for p in tv.problems(b, self.specs))
        b = _baseline(
            {
                **self.complete,
                "a/agreed": {"go": {"outcome": "invalid", "ticket": "DSPX-9"}},
            }
        )
        assert tv.problems(b, self.specs) == []

    def test_layer_override_needs_a_ticket(self):
        b = _baseline(
            {
                **self.complete,
                "a/agreed": {"go": {"outcome": "valid", "layer": "archive"}},
            }
        )
        assert any("without a ticket" in p for p in tv.problems(b, self.specs))

    def test_open_cases_need_an_answer_from_every_seeded_sdk(self):
        problems = tv.problems(_baseline({}), self.specs)
        assert any(p.startswith("a/open.go") for p in problems)
        assert any(p.startswith("a/pin.go") for p in problems)
        assert not any(".java" in p for p in problems), "java is pending"

    def test_orphans_and_unknown_sdks(self):
        b = _baseline(
            {
                **self.complete,
                "a/gone": {"go": "valid"},
                "a/pin": {"rust": "valid", "go": "valid"},
            }
        )
        problems = tv.problems(b, self.specs)
        assert any("not in the corpus" in p for p in problems)
        assert any("no such SDK" in p for p in problems)

    def test_cell_repeating_the_agreed_answer(self):
        b = _baseline(
            {
                **self.complete,
                "a/agreed": {"go": {"outcome": "valid", "ticket": "DSPX-9"}},
            }
        )
        assert any("delete the cell" in p for p in tv.problems(b, self.specs))


# --- judging --------------------------------------------------------------------


def _result(outcome: tv.Outcome, reason: str = "") -> tv.ValidateResult:
    code = {"valid": 0, "invalid": 3}.get(outcome, 1)
    return tv.ValidateResult(outcome, reason, code)


class TestJudge:
    spec = corpus.Case("a/b", b"", "invalid", "x", layer="archive")
    patterns = {"status": "seeded", "reason_patterns": {"archive": "zip"}}

    def _b(self, cells: dict[str, Any] | None = None) -> tv.Baseline:
        return _baseline(cells or {}, go=self.patterns, java={"status": "pending"})

    def test_match(self):
        v = tv.judge(
            self.spec, "go", "go@main", _result("invalid", "zip: no"), self._b()
        )
        assert (v.status, v.ok, v.build) == ("match", True, "go@main")

    def test_new_divergence(self):
        v = tv.judge(self.spec, "go", "go@main", _result("valid"), self._b())
        assert v.status == "drift" and not v.ok
        assert "A new divergence" in v.message

    def test_fixed_divergence(self):
        b = self._b({"a/b": {"go": {"outcome": "valid", "ticket": "DSPX-7"}}})
        v = tv.judge(self.spec, "go", "go@main", _result("invalid", "zip"), b)
        assert v.status == "drift"
        assert "DSPX-7 no longer reproduces" in v.message

    def test_known_divergence_matches(self):
        b = self._b({"a/b": {"go": {"outcome": "valid", "ticket": "DSPX-7"}}})
        v = tv.judge(self.spec, "go", "go@main", _result("valid"), b)
        assert (v.status, v.ticket) == ("match", "DSPX-7")

    def test_open_case_changing_is_the_finding(self):
        spec = corpus.Case("a/c", b"", "undecided", "x", ticket="DSPX-5355")
        b = self._b({"a/c": {"go": "invalid"}})
        v = tv.judge(spec, "go", "go@main", _result("valid"), b)
        assert v.status == "drift" and "no agreed answer" in v.message

    def test_error_fails_even_when_pending(self):
        v = tv.judge(
            self.spec,
            "java",
            "java@main",
            tv.ValidateResult("error", "exit 1", 1, "trace"),
            self._b(),
        )
        assert (
            v.status == "drift"
            and "could not check" in v.message
            and "trace" in v.message
        )

    def test_pinned_error_matches(self):
        b = self._b({"a/b": {"go": {"outcome": "error", "ticket": "DSPX-8"}}})
        v = tv.judge(
            self.spec, "go", "go@main", tv.ValidateResult("error", "boom", 2), b
        )
        assert v.status == "match"

    def test_pending_is_recorded_not_judged(self):
        v = tv.judge(self.spec, "java", "java@main", _result("valid"), self._b())
        assert (v.status, v.ok) == ("pending", True)

    def test_reason_at_the_wrong_layer(self):
        v = tv.judge(
            self.spec, "go", "go@main", _result("invalid", "schema says no"), self._b()
        )
        assert v.status == "reason" and not v.ok

    def test_reason_check_honours_a_layer_override(self):
        b = _baseline(
            {
                "a/b": {
                    "go": {
                        "outcome": "invalid",
                        "layer": "manifest-json",
                        "ticket": "DSPX-5",
                    }
                }
            },
            go={"status": "seeded", "reason_patterns": {"manifest-json": "JSON"}},
        )
        assert (
            tv.judge(self.spec, "go", "g", _result("invalid", "bad JSON"), b).status
            == "match"
        )
        assert (
            tv.judge(self.spec, "go", "g", _result("invalid", "zip"), b).status
            == "reason"
        )

    def test_no_pattern_no_reason_check(self):
        b = _baseline({}, go={"status": "seeded"})
        assert tv.judge(self.spec, "go", "g", _result("invalid", "anything"), b).ok

    def test_writer_is_carried(self):
        v = tv.judge(
            self.spec, "go", "g", _result("invalid", "zip"), self._b(), writer="js"
        )
        assert v.writer == "js"


# --- report and refresh ----------------------------------------------------------


def _verdicts() -> list[tv.Verdict]:
    b = _baseline(
        {}, go={"status": "seeded"}, js={"status": "seeded"}, java={"status": "pending"}
    )
    s1 = corpus.Case("a/one", b"", "valid", "x")
    s2 = corpus.Case("a/two", b"", "invalid", "x", layer="archive")
    return [
        tv.judge(s2, "js", "js@main", _result("invalid", "zip"), b),
        tv.judge(s1, "go", "go@main", _result("valid"), b),
        tv.judge(s2, "go", "go@main", _result("valid"), b),
        tv.judge(s1, "java", "java@main", _result("invalid", "nope"), b),
        tv.judge(s1, "js", "js@main", _result("valid"), b, writer="go"),
    ]


class TestReport:
    def test_encode_collect_round_trip(self):
        props: list[tuple[str, object]] = [("other", "x")]
        props += [(tv.PROPERTY, tv.encode(v)) for v in _verdicts()]
        assert tv.collect(props) == _verdicts()

    def test_table_is_stable_and_complete(self):
        r1 = tv.report(_verdicts(), "abc")
        r2 = tv.report(list(reversed(_verdicts())), "abc")
        assert r1 == r2
        assert r1["corpus_digest"] == "abc"
        assert r1["builds"]["go@main"] == {"drift": 1, "match": 1}
        assert r1["table"]["a/two"]["go@main"]["status"] == "drift"
        assert "js@main<-go" in r1["table"]["a/one"]

    def test_summaries_name_the_failures(self):
        lines = tv.terminal_lines(_verdicts())
        assert any("drift" in line and "a/two" in line for line in lines)
        assert any("no baseline yet" in line for line in lines)
        md = tv.markdown(_verdicts())
        assert "| `a/two` | go@main | valid | invalid |" in md

    def test_write(self, tmp_path: Path):
        p = tv.write_report(tmp_path / "x" / "r.json", _verdicts())
        assert json.loads(p.read_text())["format"] == 1


class TestRefresh:
    specs: list[tv.Spec] = [
        corpus.Case("a/one", b"", "valid", "x"),
        corpus.Case("a/two", b"", "invalid", "x", layer="archive"),
    ]

    def _v(
        self,
        case_id: str,
        sdk: str,
        observed: tv.Outcome,
        status: tv.Status = "drift",
        expected: tv.Expected = "pending",
    ) -> tv.Verdict:
        return tv.Verdict(
            case_id, sdk, f"{sdk}@main", "valid", expected, observed, status
        )

    def test_fixed_divergence_disappears(self):
        b = _baseline({"a/two": {"go": {"outcome": "valid", "ticket": "DSPX-1"}}})
        out = tv.refresh(b, self.specs, [self._v("a/two", "go", "invalid")])
        assert out.cells == {}

    def test_new_divergence_is_recorded_without_a_ticket(self):
        out = tv.refresh(_baseline({}), self.specs, [self._v("a/one", "go", "invalid")])
        assert out.cells == {"a/one": {"go": tv.Cell("invalid")}}
        assert any("without a ticket" in p for p in tv.problems(out, self.specs))

    def test_existing_ticket_survives_an_outcome_change(self):
        b = _baseline({"a/one": {"go": {"outcome": "invalid", "ticket": "DSPX-1"}}})
        out = tv.refresh(
            b, self.specs, [self._v("a/one", "go", "error", expected="invalid")]
        )
        assert out.cells == b.cells, "a broken run is not a baseline"
        b = _baseline({"a/one": {"go": {"outcome": "error", "ticket": "DSPX-1"}}})
        out = tv.refresh(
            b, self.specs, [self._v("a/one", "go", "invalid", expected="error")]
        )
        assert out.cells["a/one"]["go"] == tv.Cell("invalid", "DSPX-1")

    def test_seed_flips_pending_and_records_disagreements(self):
        verdicts = [
            self._v("a/one", "java", "valid", "pending", "pending"),
            self._v("a/two", "java", "valid", "pending", "pending"),
        ]
        out = tv.refresh(_baseline({}), self.specs, verdicts, seed=["java"])
        assert out.sdks["java"].status == "seeded"
        assert out.cells == {"a/two": {"java": tv.Cell("valid")}}

    def test_matches_are_left_alone(self):
        b = _baseline({})
        assert (
            tv.refresh(b, self.specs, [self._v("a/one", "go", "valid", "match")]) == b
        )

    def test_cli(self, tmp_path: Path):
        """The documented refresh command, end to end on a copy."""
        base = tmp_path / "b.json"
        shutil.copy(tv.BASELINE_PATH, base)
        report = tmp_path / "r.json"
        spec = BY_ID["json/trailing-garbage"]
        b = tv.load_baseline(base)
        fixed = tv.judge(
            spec, "go", "go@main", _result("invalid", "could not validate manifest"), b
        )
        assert fixed.status == "drift"
        tv.write_report(report, [fixed])
        assert tv._main([str(report), "--baseline", str(base)]) == 0
        assert "json/trailing-garbage" not in tv.load_baseline(base).cells


# --- the shims ---------------------------------------------------------------------

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _exe(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(0o755)
    return path


#: A stand-in CLI: ``validate`` echoes $FAKE_OUT and exits $FAKE_EXIT; help
#: output includes a validate usage line, and ``supports tdf_validity`` (which
#: java's jar answers itself) succeeds, only when $FAKE_HAS_VALIDATE is set.
_FAKE = """
case "$*" in
  "supports tdf_validity")
    [ -n "$FAKE_HAS_VALIDATE" ] && exit 0
    exit 1 ;;
  *help*)
    echo "Usage:"
    echo "  tool [command]"
    if [ -n "$FAKE_HAS_VALIDATE" ]; then echo "$FAKE_HELP_LINE"; fi
    exit 0 ;;
esac
for a in "$@"; do [ "$a" = validate ] && { printf '%s\\n' "$FAKE_OUT"; exit "$FAKE_EXIT"; }; done
echo "unexpected: $*" >&2; exit 64
"""


@pytest.fixture
def shim_root(tmp_path: Path) -> Path:
    """A throwaway xtest root, so java's shim can find a pyproject and test.env."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "xtest"\n')
    (tmp_path / "test.env").write_text("")
    return tmp_path


def _shim(root: Path, sdk: str) -> Path:
    dist = root / "sdk" / sdk / "dist" / "fake"
    dist.mkdir(parents=True)
    shutil.copy(XTEST / "sdk" / sdk / "cli.sh", dist / "cli.sh")
    if sdk == "go":
        _exe(dist / "otdfctl", _FAKE)
    elif sdk == "js":
        _exe(dist / "node_modules" / ".bin" / "opentdf", _FAKE)
    else:
        (dist / "cmdline.jar").write_bytes(b"")
        _exe(root / "bin" / "java", "shift 2\n" + _FAKE)  # drop "-jar cmdline.jar"
    return dist / "cli.sh"


_HELP_LINES = {
    "go": "  otdfctl validate <file> [flags]",
    "java": "",  # java's jar answers `supports tdf_validity` itself
    "js": "  opentdf validate [file]  Check whether a file is a valid TDF",
}


def _run(
    cli: Path, root: Path, *args: str, **env: str
) -> subprocess.CompletedProcess[bytes]:
    full = {
        "PATH": f"{root / 'bin'}:{os.environ['PATH']}",
        "TMPDIR": str(root),
        "HOME": str(root),
        **env,
    }
    return subprocess.run([str(cli), *args], capture_output=True, env=full, timeout=60)


@needs_bash
@pytest.mark.parametrize("sdk", ["go", "java", "js"])
class TestShims:
    def test_supports_needs_the_validate_command(self, sdk: str, shim_root: Path):
        cli = _shim(shim_root, sdk)
        assert _run(cli, shim_root, "supports", "tdf_validity").returncode != 0
        present = _run(
            cli,
            shim_root,
            "supports",
            "tdf_validity",
            FAKE_HAS_VALIDATE="1",
            FAKE_HELP_LINE=_HELP_LINES[sdk],
        )
        assert present.returncode == 0, present.stderr

    @pytest.mark.parametrize(
        ("out", "code", "outcome"),
        [
            ('{"valid":true}', 0, "valid"),
            ('{"valid":false,"reason":"r"}', 3, "invalid"),
            ("", 1, "error"),
        ],
    )
    def test_validate_passes_through(
        self, sdk: str, shim_root: Path, out: str, code: int, outcome: str
    ):
        cli = _shim(shim_root, sdk)
        target = shim_root / "x.tdf"
        target.write_bytes(b"")
        run = _run(
            cli, shim_root, "validate", str(target), FAKE_OUT=out, FAKE_EXIT=str(code)
        )
        assert run.returncode == code, run.stderr
        assert (
            tv.parse_output(run.returncode, run.stdout, run.stderr).outcome == outcome
        )
        if out:
            assert run.stdout == (out + "\n").encode(), (
                "stdout must pass through untouched"
            )

    def test_validate_needs_exactly_one_file(self, sdk: str, shim_root: Path):
        cli = _shim(shim_root, sdk)
        run = _run(cli, shim_root, "validate")
        assert run.returncode not in (0, 3)
        assert run.stdout == b""
