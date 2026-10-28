"""Characterization tests for the ``cli.sh supports`` capability matrix.

DSPX-4792 replaces ``sdk/{go,java,js}/cli.sh`` with native Python adapters one
SDK at a time. The capability layer is the risky half of that: 388 of the 846
lines of shell are ``supports`` case arms, and what they answer decides which
matrix cells run for real and which report a green skip. A gate that silently
flips from "yes" to "no" does not fail anything -- it deletes coverage.

``supports_matrix.json`` is the safety net. It records, for all 78
(SDK x feature) pairs, the gate the shell encodes today and the answer it
yields at representative versions. This module is what makes the file trustworthy:
every claim in it is re-derived here from ``sdk/*/cli.sh`` and ``tdfs.py``, so
the snapshot cannot rot into a stale comment.

It records current behaviour, *bugs included*. Two version gates disagree with
the comment sitting above them (:data:`KNOWN_COMMENT_DIVERGENCES`); the snapshot
pins the code, names the divergence, and a test asserts the set of them does not
grow. Fixing one is a deliberate edit to this file plus a note in the PR that
changed the skip counts.

Everything except :class:`TestInstalledBuildAgreement` is offline: no platform,
no SDK build, no network.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, get_args

import pytest

import tdfs

HERE = Path(__file__).parent
MATRIX_PATH = HERE / "supports_matrix.json"
MATRIX: dict[str, Any] = json.loads(MATRIX_PATH.read_text())
GATES: list[dict[str, Any]] = MATRIX["gates"]

#: Version gates whose awk expression contradicts the comment above it.
#: ``(sdk, feature) -> (what the comment claims, what the code does)``.
KNOWN_COMMENT_DIVERGENCES = {
    ("go", "hexless"): ("4.3.0", "4.2.0"),
    ("go", "better-messages-2024"): ("0.3.28", "0.3.18"),
}

#: Exit status each deterministic gate kind produces from ``cli.sh supports``.
DETERMINISTIC_EXIT = {"always", "unprobeable", "absent"}


def gate_id(g: dict[str, Any]) -> str:
    return f"{g['sdk']}-{g['feature']}"


ALL_GATES = pytest.mark.parametrize("gate", GATES, ids=gate_id)


# --------------------------------------------------------------------- awk


def awk_predicate(program: str):
    """Compile one of the shims' awk version gates into a Python predicate.

    The shims all run the same shape -- ``awk -F. '{ if (COND) exit 0; else
    exit 1; }'`` over a single ``major.minor.patch`` line -- so ``COND`` needs
    only ``$1``/``$2``/``$3``, integer literals, comparisons, ``&&`` and
    ``||``. Anything outside that vocabulary is rejected rather than guessed
    at, because a gate this code cannot model is a gate the snapshot cannot
    claim to have characterized.

    Only well-formed numeric triples are accepted. On anything else awk's own
    answer is neither obvious nor portable -- see
    ``test_non_numeric_version_satisfies_every_gate``.
    """
    m = re.fullmatch(r"\{ if \((.*)\) exit 0; else exit 1; \}", program.strip())
    if not m:
        raise ValueError(f"unrecognised awk program: {program!r}")
    py = re.sub(r"\$([123])", r"f\1", m.group(1))
    py = py.replace("&&", " and ").replace("||", " or ")
    tree = ast.parse(py, mode="eval")
    allowed = (
        ast.Expression,
        ast.BoolOp,
        ast.And,
        ast.Or,
        ast.Compare,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.Gt,
        ast.GtE,
        ast.Lt,
        ast.LtE,
        ast.Eq,
        ast.NotEq,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError(f"unsupported awk construct {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in {"f1", "f2", "f3"}:
            raise ValueError(f"unsupported awk field {node.id}")
    code = compile(tree, "<awk>", "eval")

    def predicate(version: str) -> bool:
        major, minor, patch = (int(p) for p in version.split("."))
        return bool(
            eval(code, {"__builtins__": {}}, {"f1": major, "f2": minor, "f3": patch})
        )

    return predicate


def version_grid() -> list[str]:
    """Versions dense enough to pin every threshold the shims use.

    Thresholds run from 0.3.18 to 4.3.0, so the grid has to straddle each of
    them on all three components -- a gate that is off by one patch is exactly
    the bug this file exists to catch.
    """
    return [
        f"{major}.{minor}.{patch}"
        for major in range(0, 6)
        for minor in range(0, 24)
        for patch in range(0, 32)
    ]


GRID = version_grid()


def min_version_gates() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Every ``min_version`` gate, including the ones nested inside ``all_of``."""
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for g in GATES:
        for sub in [g["shell"], *g["shell"].get("of", [])]:
            if sub["kind"] == "min_version":
                out.append((g, sub))
    return out


MIN_VERSION_GATES = pytest.mark.parametrize(
    ("gate", "vgate"),
    min_version_gates(),
    ids=lambda x: x["feature"] if "feature" in x else x.get("min_version", ""),
)


# ------------------------------------------------------- shell arm extraction


def read_shell(sdk: str) -> list[str]:
    return (HERE / "sdk" / sdk / "cli.sh").read_text().splitlines()


def extract_arms(sdk: str) -> dict[str, tuple[str, int, int]]:
    """``feature -> (case pattern, first line, last line)`` from ``cli.sh``.

    Parsed rather than sourced. Running the real shim would need an installed
    SDK build, which is the thing these tests must not require.
    """
    lines = read_shell(sdk)
    start_line, end_line = MATRIX["shell_sources"][sdk]["supports_block"]
    arms: dict[str, tuple[str, int, int]] = {}
    pattern: str | None = None
    start = 0
    for i in range(start_line - 1, end_line):
        line = lines[i]
        m = re.match(r"^    ([^\s(].*?)\)$", line)
        if m:
            pattern, start = m.group(1), i + 1
            continue
        if line.strip() == ";;" and pattern is not None:
            for name in (p.strip() for p in pattern.split("|")):
                arms[name] = (pattern, start, i + 1)
            pattern = None
    return arms


ARMS = {sdk: extract_arms(sdk) for sdk in MATRIX["sdks"]}

#: Versions the override oracle needs a stub tree for: ``main`` as the control,
#: plus every version a version-conditional override is scoped to.
STUB_VERSIONS = {"main"} | {
    g["python_override"]["when_version"]
    for g in GATES
    if (g.get("python_override") or {}).get("when_version")
}


@pytest.fixture(scope="session")
def stubs(tmp_path_factory: pytest.TempPathFactory) -> dict[int, Path]:
    """Two stub SDK trees: one whose ``cli.sh supports`` always succeeds, one
    that always fails. Built once -- writing and exec'ing a fresh script costs
    real time on some platforms, and the oracle needs 156 of them."""
    roots: dict[int, Path] = {}
    for code in (0, 1):
        root = tmp_path_factory.mktemp(f"stub{code}")
        for sdk in MATRIX["sdks"]:
            for version in STUB_VERSIONS:
                cli = root / "sdk" / sdk / "dist" / version / "cli.sh"
                cli.parent.mkdir(parents=True, exist_ok=True)
                cli.write_text(f"#!/bin/sh\nexit {code}\n")
                cli.chmod(0o755)
        roots[code] = root
    return roots


def arm_body(gate: dict[str, Any]) -> str:
    start, end = gate["shell"]["arm_lines"]
    return "\n".join(read_shell(gate["sdk"])[start - 1 : end])


def arm_code(gate: dict[str, Any]) -> str:
    """The arm with comment lines removed.

    The ``gmac_root_rejected`` arms explain at length that there is nothing to
    grep for, so a naive search for "grep" finds the prose rather than a probe.
    """
    return "\n".join(
        line
        for line in arm_body(gate).splitlines()
        if not line.lstrip().startswith("#")
    )


# ------------------------------------------------------------------ the tests


class TestSnapshotShape:
    """The snapshot covers the whole matrix and nothing outside it."""

    def test_covers_every_sdk_and_feature(self):
        assert MATRIX["sdks"] == list(get_args(tdfs.sdk_type))
        assert MATRIX["features"] == list(get_args(tdfs.feature_type))
        expected = {(s, f) for s in MATRIX["sdks"] for f in MATRIX["features"]}
        assert {(g["sdk"], g["feature"]) for g in GATES} == expected
        assert len(GATES) == len(expected), "one row per (sdk, feature), no duplicates"

    def test_shell_sources_are_current(self):
        for sdk, src in MATRIX["shell_sources"].items():
            lines = read_shell(sdk)
            assert len(lines) == src["lines"], f"{sdk}/cli.sh changed length"
            start, end = src["supports_block"]
            assert re.fullmatch(
                r'if \[\[? "\$1" == "supports" \]\]?; then', lines[start - 1].strip()
            ), f"{sdk}/cli.sh supports block does not start where recorded"
            assert lines[end - 1].strip() == "fi"

    def test_every_case_arm_is_accounted_for(self):
        """No arm in the shell is missing from the snapshot, and vice versa."""
        for sdk in MATRIX["sdks"]:
            in_shell = set(ARMS[sdk]) - {"*"}
            in_snapshot = {
                g["feature"]
                for g in GATES
                if g["sdk"] == sdk and g["shell"]["kind"] != "absent"
            }
            assert in_shell == in_snapshot

    def test_unknown_features_fall_through_to_a_wildcard(self):
        """The ``absent`` rows are only safe because every shim has a ``*`` arm."""
        for sdk in MATRIX["sdks"]:
            assert "*" in ARMS[sdk]
            body = "\n".join(read_shell(sdk)[slice(*[x - 1 for x in ARMS[sdk]["*"][1:]])])
            assert "exit 2" in body


class TestShellAgreement:
    """Each row describes the arm that is actually in ``cli.sh``."""

    @ALL_GATES
    def test_arm_matches(self, gate: dict[str, Any]):
        shell = gate["shell"]
        arms = ARMS[gate["sdk"]]
        if shell["kind"] == "absent":
            assert gate["feature"] not in arms
            return
        pattern, start, end = arms[gate["feature"]]
        assert shell["arm"] == pattern
        assert shell["arm_lines"] == [start, end]
        assert start <= shell["line"] <= end
        for sub in shell.get("of", []):
            assert start <= sub["line"] <= end

    @ALL_GATES
    def test_kind_evidence_is_present_in_the_arm(self, gate: dict[str, Any]):
        shell = gate["shell"]
        if shell["kind"] == "absent":
            return
        body = arm_body(gate)
        for sub in [shell, *shell.get("of", [])]:
            match sub["kind"]:
                case "min_version":
                    assert sub["awk"] in body
                    assert sub["version_probe"]["jq"] in body
                    for word in sub["version_probe"]["argv"]:
                        assert word in body
                case "help_contains":
                    assert sub["needle"] in body
                    assert sub["grep"] in body
                    for word in sub["help_argv"]:
                        assert word in body
                case "delegate":
                    for word in sub["delegate_argv"]:
                        assert word in body
                case "always":
                    code = arm_code(gate)
                    assert f"exit {0 if sub['answer'] else 1}" in code
                    assert "awk" not in code and "grep" not in code, (
                        "an Always gate must not probe the build"
                    )
                case "unprobeable":
                    code = arm_code(gate)
                    assert "exit 1" in code
                    assert "awk" not in code and "grep" not in code
                case "all_of":
                    pass
                case other:  # pragma: no cover - guards a typo in the snapshot
                    pytest.fail(f"unknown gate kind {other!r}")

    @ALL_GATES
    def test_deterministic_gates_record_their_exit_code(self, gate: dict[str, Any]):
        shell = gate["shell"]
        if shell["kind"] not in DETERMINISTIC_EXIT:
            assert "exit_code" not in shell, (
                "only always/unprobeable/absent gates answer without running the SDK"
            )
            return
        expected = 2 if shell["kind"] == "absent" else (0 if shell["answer"] else 1)
        assert shell["exit_code"] == expected


class TestVersionGates:
    """Each awk expression is exactly the predicate ``version >= min_version``."""

    @MIN_VERSION_GATES
    def test_awk_is_a_clean_threshold(
        self, gate: dict[str, Any], vgate: dict[str, Any]
    ):
        predicate = awk_predicate(vgate["awk"])
        threshold = tuple(int(p) for p in vgate["min_version"].split("."))
        wrong = [
            v
            for v in GRID
            if predicate(v) != (tuple(int(p) for p in v.split(".")) >= threshold)
        ]
        assert not wrong[:5], (
            f"{gate_id(gate)}: awk disagrees with MinVersion({vgate['min_version']}) "
            f"at {wrong[:5]}"
        )

    @MIN_VERSION_GATES
    def test_recorded_samples_are_what_awk_answers(
        self, gate: dict[str, Any], vgate: dict[str, Any]
    ):
        predicate = awk_predicate(vgate["awk"])
        for version, expected in vgate["samples"]:
            assert predicate(version) is expected, f"{gate_id(gate)} at {version}"

    @MIN_VERSION_GATES
    def test_samples_straddle_the_threshold(
        self, gate: dict[str, Any], vgate: dict[str, Any]
    ):
        answers = {a for _, a in vgate["samples"]}
        assert answers == {True, False}, (
            "a sample set that never changes answer proves nothing about the gate"
        )

    def test_comment_divergences_are_the_known_ones(self):
        """The two gates whose comment lies are named; a third must not appear.

        Fixing one of these changes which cells run, so it has to be a
        deliberate edit here rather than something that slips through.
        """
        found = {
            (g["sdk"], g["feature"]): (v["comment_claims"], v["min_version"])
            for g, v in min_version_gates()
            if not v["comment_matches_code"]
        }
        assert found == KNOWN_COMMENT_DIVERGENCES

    @MIN_VERSION_GATES
    def test_comment_claim_is_recorded_faithfully(
        self, gate: dict[str, Any], vgate: dict[str, Any]
    ):
        """``comment_claims`` is a real version mentioned near the gate."""
        if vgate["comment_matches_code"]:
            return
        body = arm_body(gate)
        assert vgate["comment_claims"] in body
        assert vgate["min_version"] not in body, (
            "if the code's own threshold appears in the arm text the divergence "
            "is not what this row says it is"
        )

    def test_non_numeric_version_satisfies_every_gate(self):
        """A branch build reporting a non-numeric version passes every gate.

        POSIX says a comparison between a field that does not look numeric and
        a numeric constant is a *string* comparison, so ``$1 > 0`` with
        ``$1 == "main"`` is ``"main" > "0"`` -- true. Same for a ``v``-prefixed
        tag. The whole ``FORCED_SUPPORTS`` escape hatch is documented on the
        premise that the shims "say no for precisely the unreleased builds a
        fix needs to be evaluated against"; for any SDK whose ``--version``
        does not emit a bare numeric triple, they say yes to everything
        instead. The native gates must decide this explicitly rather than
        inherit it from awk.
        """
        if not _have("awk"):
            pytest.skip("awk not available")
        for _, vgate in min_version_gates():
            program = vgate["awk"].replace("exit 0;", "print 1;").replace(
                "exit 1;", "print 0;"
            )
            out = subprocess.run(
                ["awk", "-F.", program],
                input="main\nv0.0.0\n0.0.0\n",
                capture_output=True,
                text=True,
                check=True,
            ).stdout.split()
            assert out[:2] == ["1", "1"], vgate["awk"]

    @MIN_VERSION_GATES
    def test_awk_matches_real_awk(self, gate: dict[str, Any], vgate: dict[str, Any]):
        """The Python model of awk is a model, so check it against awk."""
        if not _have("awk"):
            pytest.skip("awk not available")
        predicate = awk_predicate(vgate["awk"])
        sample = [v for i, v in enumerate(GRID) if i % 7 == 0]
        program = vgate["awk"].replace("exit 0;", "print 1;").replace(
            "exit 1;", "print 0;"
        )
        out = subprocess.run(
            ["awk", "-F.", program],
            input="\n".join(sample) + "\n",
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        assert len(out) == len(sample)
        for version, answer in zip(sample, out, strict=True):
            assert predicate(version) is (answer == "1"), version


class TestPythonOverrides:
    """``tdfs._uncached_supports``'s match table is exactly what the snapshot says.

    A6 folds this table into the gate tables, so it has to be enumerated
    somewhere a test can check. The oracle runs ``_uncached_supports`` twice
    against stub shims -- one that always exits 0, one that always exits 1. If
    both runs agree, the Python match arm decided and never reached the shell;
    if they differ, execution fell through.
    """

    @staticmethod
    def _decide(
        stubs: dict[int, Path],
        monkeypatch: pytest.MonkeyPatch,
        sdk: str,
        feature: str,
        version: str,
    ) -> bool | None:
        answers: set[bool] = set()
        for code, root in stubs.items():
            monkeypatch.chdir(root)
            answers.add(tdfs.SDK(sdk, version)._uncached_supports(feature))
        return answers.pop() if len(answers) == 1 else None

    @ALL_GATES
    def test_override_table(
        self, gate: dict[str, Any], stubs: dict[int, Path], monkeypatch: pytest.MonkeyPatch
    ):
        override = gate.get("python_override")
        version = (override or {}).get("when_version", "main")
        decided = self._decide(
            stubs, monkeypatch, gate["sdk"], gate["feature"], version
        )
        if override is None:
            assert decided is None, (
                f"{gate_id(gate)} is answered by a Python match arm that the "
                "snapshot does not record"
            )
        else:
            assert decided is override["answer"]

    @ALL_GATES
    def test_version_conditional_override_does_not_leak(
        self, gate: dict[str, Any], stubs: dict[int, Path], monkeypatch: pytest.MonkeyPatch
    ):
        override = gate.get("python_override")
        if not override or "when_version" not in override:
            return
        assert (
            self._decide(stubs, monkeypatch, gate["sdk"], gate["feature"], "main")
            is None
        ), "the override fires for versions it is not scoped to"

    def test_override_lines_point_at_a_case_arm(self):
        source = (HERE / "tdfs.py").read_text().splitlines()
        for gate in GATES:
            override = gate.get("python_override")
            if not override:
                continue
            line = source[override["line"] - 1]
            assert line.strip().startswith("case (")
            assert f'"{gate["feature"]}"' in line
            assert f'"{gate["sdk"]}"' in line

    def test_relations_to_the_shell_are_classified(self):
        """Every override says whether it duplicates, contradicts or extends the shell.

        A6 cannot fold this table in without knowing which: the duplicates just
        disappear, the contradiction has to survive as a denylist, and the rest
        become new rows.
        """
        counts: dict[str, int] = {}
        for gate in GATES:
            if not gate.get("python_override"):
                continue
            counts[gate["override_relation"]] = (
                counts.get(gate["override_relation"], 0) + 1
            )
        assert counts == {
            "redundant": 5,
            "redundant-with-default": 1,
            "contradicts": 1,
            "supplies-a-missing-answer": 6,
        }


class TestArgvPathProbes:
    """The four capability probes that live outside the ``supports`` verb.

    These sit in the encrypt/decrypt argv path and change the command line, so
    a native adapter that ports only the ``supports`` arms will build different
    argv than the shim it replaces and the A2 argv diff will go red.
    """

    @pytest.mark.parametrize(
        "probe", MATRIX["argv_path_probes"], ids=lambda p: f"{p['sdk']}-{p['line']}"
    )
    def test_probe_is_where_the_snapshot_says(self, probe: dict[str, Any]):
        line = read_shell(probe["sdk"])[probe["line"] - 1]
        assert probe["probe"] in line
        start, end = MATRIX["shell_sources"][probe["sdk"]]["supports_block"]
        assert not start <= probe["line"] <= end, (
            "this is meant to be a probe outside the supports block"
        )


class TestInstalledBuildAgreement:
    """Run the real shim, when there is one, and check it against the snapshot.

    Skips cleanly everywhere a build is not installed, which is every developer
    checkout and every CI job that did not install that SDK.
    """

    @ALL_GATES
    def test_real_shim_agrees(self, gate: dict[str, Any]):
        dist = HERE / "sdk" / gate["sdk"] / "dist"
        installed = sorted(p for p in dist.glob("*/cli.sh")) if dist.is_dir() else []
        if not installed:
            pytest.skip(f"no {gate['sdk']} build installed under sdk/{gate['sdk']}/dist")
        shell = gate["shell"]
        for cli in installed:
            result = subprocess.run(
                [str(cli), "supports", gate["feature"]],
                capture_output=True,
                cwd=HERE,
                timeout=300,
            )
            if shell["kind"] in DETERMINISTIC_EXIT:
                assert result.returncode == shell["exit_code"], (
                    f"{cli}: expected exit {shell['exit_code']} for a "
                    f"{shell['kind']} gate, got {result.returncode}"
                )
            else:
                assert result.returncode in (0, 1), (
                    f"{cli}: exit 2 means the arm the snapshot records is gone"
                )


def _have(tool: str) -> bool:
    return any(
        os.access(os.path.join(d, tool), os.X_OK)
        for d in os.environ.get("PATH", "").split(os.pathsep)
        if d
    )
