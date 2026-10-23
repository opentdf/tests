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
import zipinspect
from validity import baseline as vb
from validity import corpus, zipbuild
from validity.contract import ValidateResult, parse_output, validate

XTEST = Path(__file__).parent.parent
CASES = corpus.corpus()
BY_ID = {c.id: c for c in CASES}


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
        assert [(c.id, c.data) for c in again] == [(c.id, c.data) for c in CASES]

    def test_filenames_are_unique(self):
        assert len({c.filename for c in CASES}) == len(CASES)

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
        base = zipbuild.build_zip([zipbuild.Entry("a", b"x")])
        lied = zipbuild.build_zip([zipbuild.Entry("a", b"x")], entry_count=9)
        cd = dict(base.boundaries)["cd"]
        assert lied.data[:cd] == base.data[:cd]
        assert lied.data != base.data

    def test_boundaries_are_in_file_order(self):
        built = zipbuild.build_zip(
            [zipbuild.Entry("a", b"x", zip64=True, data_descriptor=True)],
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


class TestPinnedInputs:
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
        r = parse_output(0, b'{"valid":true}\n')
        assert (r.outcome, r.reason) == ("valid", "")

    def test_invalid_with_reason(self):
        r = parse_output(3, b'{"valid":false,"reason":"zip: bad"}\n')
        assert (r.outcome, r.reason) == ("invalid", "zip: bad")

    def test_invalid_without_reason(self):
        assert parse_output(3, b'{"valid":false}').outcome == "invalid"

    @pytest.mark.parametrize("code", [1, 2, 4, 127])
    def test_other_exits_are_errors(self, code: int):
        r = parse_output(code, b"", b"boom\n")
        assert r.outcome == "error"
        assert f"exit {code}" in r.reason
        assert r.stderr == "boom"

    def test_exit_1_with_invalid_json_is_still_an_error(self):
        """The whole reason the contract does not use 1 for invalid."""
        assert parse_output(1, b'{"valid":false}').outcome == "error"

    def test_signal(self):
        r = parse_output(-9, b"")
        assert (r.outcome, r.reason) == ("error", "killed by SIGKILL")

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
        r = parse_output(code, stdout)
        assert r.outcome == "error"
        assert why in r.reason

    def test_long_reasons_are_trimmed(self):
        long = "x" * 5000
        r = parse_output(
            3, json.dumps({"valid": False, "reason": "zip: " + long}).encode()
        )
        assert r.outcome == "invalid" and len(r.reason) < 500
        assert r.reason.startswith("zip: "), "the start says which layer rejected it"


def _fake_sdk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: str) -> tdfs.SDK:
    dist = tmp_path / "sdk" / "go" / "dist" / "fake"
    dist.mkdir(parents=True)
    cli = dist / "cli.sh"
    cli.write_text("#!/usr/bin/env bash\n" + script)
    cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
    monkeypatch.chdir(tmp_path)
    return tdfs.SDK("go", "fake")


class TestValidate:
    def test_invalid(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        sdk = _fake_sdk(
            tmp_path,
            monkeypatch,
            '[ "$1" = validate ] || exit 9\n'
            'echo "{\\"valid\\":false,\\"reason\\":\\"got $2\\"}"; exit 3\n',
        )
        r = validate(sdk, Path("x.tdf"))
        assert (r.outcome, r.reason) == ("invalid", "got x.tdf")

    def test_hang_is_an_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        sdk = _fake_sdk(tmp_path, monkeypatch, "echo stuck >&2\nexec sleep 30\n")
        start = time.monotonic()
        r = validate(sdk, Path("x.tdf"), timeout=0.3)
        assert time.monotonic() - start < 10
        assert (r.outcome, r.reason, r.stderr) == (
            "error",
            "timed out after 0.3s",
            "stuck",
        )


# --- the baseline --------------------------------------------------------------

SPECS: list[vb.Spec] = [*CASES, *corpus.ROUND_TRIPS]


def _baseline(cells: dict[str, Any], **sdks: dict[str, Any]) -> vb.Baseline:
    return vb.Baseline.model_validate(
        {"format": 1, "sdks": sdks or {"go": {}}, "cells": cells}
    )


class TestCheckedInBaseline:
    def test_has_no_problems(self):
        assert vb.problems(vb.load(), SPECS) == []

    def test_describes_every_sdk(self):
        assert set(vb.load().sdks) == set(tdfs.sdk_type.__args__)


class TestBaselineParsing:
    @pytest.mark.parametrize(
        ("cell", "match"),
        [
            ("maybe", "outcome"),
            ({"outcome": "valid", "ticket": "dspx 1"}, "pattern"),
            ({"outcome": "valid", "colour": "red"}, "Extra inputs"),
            ({"outcome": "invalid", "layer": "payload"}, "layer"),
            (7, "valid dictionary"),
        ],
    )
    def test_bad_cells(self, cell: object, match: str):
        with pytest.raises(ValueError, match=match):
            _baseline({"a/b": {"go": cell}})

    def test_bad_sdk_entries(self):
        with pytest.raises(ValueError, match="Extra inputs"):
            _baseline({}, go={"status": "seeded"})
        with pytest.raises(ValueError, match="reason_patterns"):
            _baseline({}, go={"reason_patterns": {"x": "y"}})
        with pytest.raises(ValueError, match="unterminated|missing"):
            _baseline({}, go={"reason_patterns": {"archive": "("}})

    def test_bad_format(self):
        with pytest.raises(ValueError, match="format"):
            vb.Baseline.model_validate({"format": 2, "sdks": {}})

    def test_bare_outcome_is_a_cell(self):
        b = _baseline({"a/b": {"go": "valid"}})
        assert b.cells["a/b"]["go"] == vb.Cell(outcome="valid")


class TestExpected:
    spec = corpus.Case("a/b", b"", "invalid", "x", layer="archive")
    open_spec = corpus.Case("a/c", b"", "undecided", "x", ticket="DSPX-1")

    def test_without_a_cell_any_sdk_gets_the_agreed_answer(self):
        assert _baseline({}).expected(self.spec, "go") == vb.Cell(outcome="invalid")
        assert _baseline({}).expected(self.spec, "rust") == vb.Cell(outcome="invalid")

    def test_undecided_without_a_cell_has_no_expectation(self):
        assert _baseline({}).expected(self.open_spec, "go") is None

    def test_recorded_cell_wins(self):
        b = _baseline({"a/b": {"go": {"outcome": "valid", "ticket": "DSPX-2"}}})
        assert b.expected(self.spec, "go") == vb.Cell(outcome="valid", ticket="DSPX-2")


class TestProblems:
    specs: list[vb.Spec] = [
        corpus.Case("a/agreed", b"", "valid", "x"),
        corpus.Case("a/open", b"", "undecided", "x", ticket="DSPX-1"),
        corpus.Case("a/pin", b"", "unspecified", "x"),
    ]
    complete = {"a/open": {"go": "valid"}, "a/pin": {"go": "invalid"}}

    def test_complete_baseline_is_clean(self):
        assert vb.problems(_baseline(self.complete), self.specs) == []

    def test_divergence_needs_a_ticket(self):
        b = _baseline({**self.complete, "a/agreed": {"go": "invalid"}})
        assert any("without a ticket" in p for p in vb.problems(b, self.specs))
        b = _baseline(
            {
                **self.complete,
                "a/agreed": {"go": {"outcome": "invalid", "ticket": "DSPX-9"}},
            }
        )
        assert vb.problems(b, self.specs) == []

    def test_layer_override_needs_a_ticket(self):
        b = _baseline(
            {
                **self.complete,
                "a/agreed": {"go": {"outcome": "valid", "layer": "archive"}},
            }
        )
        assert any("without a ticket" in p for p in vb.problems(b, self.specs))

    def test_open_cases_need_an_answer_from_every_sdk(self):
        problems = vb.problems(_baseline({}, go={}, java={}), self.specs)
        assert sorted(p.split(":")[0] for p in problems) == [
            "a/open.go",
            "a/open.java",
            "a/pin.go",
            "a/pin.java",
        ]

    def test_orphans_and_unknown_sdks(self):
        b = _baseline(
            {
                **self.complete,
                "a/gone": {"go": "valid"},
                "a/pin": {"rust": "valid", "go": "valid"},
            }
        )
        problems = vb.problems(b, self.specs)
        assert any("not in the corpus" in p for p in problems)
        assert any("no such SDK" in p for p in problems)

    def test_cell_repeating_the_agreed_answer(self):
        b = _baseline(
            {
                **self.complete,
                "a/agreed": {"go": {"outcome": "valid", "ticket": "DSPX-9"}},
            }
        )
        assert any("delete the cell" in p for p in vb.problems(b, self.specs))


# --- judging --------------------------------------------------------------------


class TestJudge:
    spec = corpus.Case("a/b", b"", "invalid", "x", layer="archive")

    def _b(self, cells: dict[str, Any] | None = None) -> vb.Baseline:
        return _baseline(cells or {}, go={"reason_patterns": {"archive": "zip"}})

    def _judge(
        self, result: ValidateResult, b: vb.Baseline | None = None, spec=None
    ) -> str | None:
        return vb.judge(spec or self.spec, "go", "go@main", result, b or self._b())

    def test_match(self):
        assert self._judge(ValidateResult("invalid", "zip: no")) is None

    def test_new_divergence(self):
        failure = self._judge(ValidateResult("valid"))
        assert failure and "A new divergence" in failure

    def test_fixed_divergence(self):
        b = self._b({"a/b": {"go": {"outcome": "valid", "ticket": "DSPX-7"}}})
        failure = self._judge(ValidateResult("invalid", "zip"), b)
        assert failure and "DSPX-7 no longer reproduces" in failure

    def test_known_divergence_matches(self):
        b = self._b({"a/b": {"go": {"outcome": "valid", "ticket": "DSPX-7"}}})
        assert self._judge(ValidateResult("valid"), b) is None

    def test_open_case_changing_is_the_finding(self):
        spec = corpus.Case("a/c", b"", "undecided", "x", ticket="DSPX-5355")
        b = self._b({"a/c": {"go": "invalid"}})
        failure = self._judge(ValidateResult("valid"), b, spec)
        assert failure and "no agreed answer" in failure and "DSPX-5355" in failure

    def test_open_case_with_no_recorded_answer_fails(self):
        spec = corpus.Case("a/c", b"", "undecided", "x", ticket="DSPX-5355")
        failure = self._judge(ValidateResult("valid"), spec=spec)
        assert failure and "records none for go" in failure

    def test_error_fails(self):
        failure = self._judge(ValidateResult("error", "exit 1", "trace"))
        assert failure and "could not check" in failure and "trace" in failure

    def test_pinned_error_matches(self):
        b = self._b({"a/b": {"go": {"outcome": "error", "ticket": "DSPX-8"}}})
        assert self._judge(ValidateResult("error", "boom"), b) is None

    def test_reason_at_the_wrong_layer(self):
        failure = self._judge(ValidateResult("invalid", "schema says no"))
        assert failure and "archive-layer rejection" in failure

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
            go={"reason_patterns": {"manifest-json": "JSON"}},
        )
        assert self._judge(ValidateResult("invalid", "bad JSON"), b) is None
        assert self._judge(ValidateResult("invalid", "zip"), b)

    def test_no_pattern_no_reason_check(self):
        b = _baseline({}, go={})
        assert self._judge(ValidateResult("invalid", "anything"), b) is None


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
        assert parse_output(run.returncode, run.stdout, run.stderr).outcome == outcome
        if out:
            assert run.stdout == (out + "\n").encode(), (
                "stdout must pass through untouched"
            )

    def test_validate_needs_exactly_one_file(self, sdk: str, shim_root: Path):
        cli = _shim(shim_root, sdk)
        run = _run(cli, shim_root, "validate")
        assert run.returncode not in (0, 3)
        assert run.stdout == b""
