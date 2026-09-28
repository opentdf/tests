"""The gate evaluator, exercised without an SDK installed.

That is the point of gates being data. The ~50 capability answers currently
spelled as awk one-liners can only be checked by installing the build they
describe; as table rows they can be checked against a stub, which is the only
way a transcription of that size ever gets reviewed.
"""

from __future__ import annotations

import pytest

from otdf_adapter.gates import (
    Always,
    Delegate,
    GateTable,
    HelpContains,
    MinVersion,
    Unprobeable,
    evaluate,
    lookup,
)
from otdf_adapter.protocol import SdkVersion


class StubContext:
    def __init__(
        self,
        version: SdkVersion | None = None,
        help_text: dict[tuple[str, ...], str] | None = None,
        native: bool = False,
    ) -> None:
        self._version = version or SdkVersion(raw="")
        self._help = help_text or {}
        self._native = native
        self.asked: list[str] = []

    def version(self) -> SdkVersion:
        return self._version

    def help_text(self, *subcommand: str) -> str:
        return self._help.get(subcommand, "")

    def ask_native(self, feature: str) -> bool:
        self.asked.append(feature)
        return self._native


class TestMinVersion:
    @pytest.mark.parametrize(
        ("reported", "minimum", "expected"),
        [
            ("0.12.0", "0.12.0", True),
            ("0.12.1", "0.12.0", True),
            ("1.0.0", "0.12.0", True),
            ("0.11.9", "0.12.0", False),
            ("0.2.0", "0.12.0", False),
        ],
    )
    def test_boundary(self, reported: str, minimum: str, expected: bool):
        # The awk form of this comparison -- `if ($1 > 0 || ($1 == 0 && $2 >=
        # 12)) exit 0` -- is rewritten by hand per feature, which is how a
        # gate ends up comparing against 4.2 under a comment that says 4.3.
        ctx = StubContext(SdkVersion(raw="", sdk=reported))
        assert bool(evaluate(MinVersion(minimum), ctx)) is expected

    def test_v_prefix_and_prerelease_parse(self):
        ctx = StubContext(SdkVersion(raw="", sdk="v0.13.0-rc.1"))
        assert not evaluate(MinVersion("0.13.0"), ctx)
        assert evaluate(MinVersion("0.12.0"), ctx)

    def test_schema_field_is_separate_from_the_sdk_version(self):
        # `hexless` asks about the container schema, `ecwrap` about the SDK.
        # One version number cannot answer both.
        ctx = StubContext(SdkVersion(raw="", sdk="0.3.0", schema="4.3.0"))
        assert evaluate(MinVersion("4.3.0", field="schema"), ctx)
        assert not evaluate(MinVersion("4.3.0", field="sdk"), ctx)

    def test_an_unparseable_version_answers_no_with_a_reason(self):
        ctx = StubContext(SdkVersion(raw="main", sdk="main"))
        result = evaluate(MinVersion("0.12.0"), ctx)
        assert not result
        assert "does not parse" in result.reason

    def test_a_missing_version_answers_no_with_a_reason(self):
        # Every branch build. The skip message has to say so, or it reads as
        # "this feature is missing" rather than "we could not tell".
        result = evaluate(MinVersion("0.12.0"), StubContext())
        assert not result
        assert "no parseable sdk version" in result.reason


class TestHelpContains:
    def test_present_and_absent(self):
        ctx = StubContext(help_text={("decrypt",): "  --kas-allowlist strings\n"})
        assert evaluate(HelpContains(("decrypt",), "kas-allowlist"), ctx)
        assert not evaluate(HelpContains(("decrypt",), "--ecdsa-binding"), ctx)

    def test_it_asks_the_right_subcommand(self):
        ctx = StubContext(help_text={("encrypt",): "--target-mode"})
        assert evaluate(HelpContains(("encrypt",), "--target-mode"), ctx)
        assert not evaluate(HelpContains(("decrypt",), "--target-mode"), ctx)

    def test_ignore_case(self):
        ctx = StubContext(help_text={(): "HPQT:XWing"})
        assert evaluate(HelpContains((), "hpqt:xwing", ignore_case=True), ctx)
        assert not evaluate(HelpContains((), "hpqt:xwing"), ctx)

    def test_unreadable_help_answers_no(self):
        assert not evaluate(HelpContains(("decrypt",), "anything"), StubContext())

    def test_subcommand_is_normalised_to_a_tuple(self):
        # The gate has to be hashable and shareable; a list field would make
        # a frozen dataclass unhashable and let a caller mutate a table row.
        assert HelpContains(["decrypt"], "x").subcommand == ("decrypt",)


class TestAlwaysAndUnprobeable:
    def test_always(self):
        assert evaluate(Always(True, "go has always autoconfigured"), StubContext())
        assert not evaluate(Always(False), StubContext())

    def test_unprobeable_carries_its_reason(self):
        # Today this and "too old" are both a bare `exit 1`, so a skip cannot
        # say which it is. The reason is the whole added value.
        gate = Unprobeable("the check adds no CLI surface")
        result = evaluate(gate, StubContext())
        assert not result
        assert result.reason == "the check adds no CLI surface"


class TestDelegate:
    def test_it_asks_the_sdk(self):
        ctx = StubContext(native=True)
        assert evaluate(Delegate(), ctx, feature="dpop")
        assert ctx.asked == ["dpop"]

    def test_a_renamed_feature_is_passed_through(self):
        ctx = StubContext(native=False)
        assert not evaluate(Delegate("dpop_nonce_challenge"), ctx, feature="nonce")
        assert ctx.asked == ["dpop_nonce_challenge"]


class TestTables:
    def test_lookup_returns_none_for_an_unknown_pair(self):
        # Which is what keeps a partially-populated table working: no entry
        # means fall back to the shim, so the tables can be filled one row at
        # a time instead of in a flag day.
        assert lookup("go", "ecwrap", {}) is None
        assert lookup("go", "ecwrap", {"go": {}}) is None

    def test_a_table_evaluates_its_own_rows(self):
        table = GateTable("go", {"autoconfigure": Always(True, "always has")})
        assert table.evaluate("autoconfigure", StubContext())
        assert table.evaluate("ecwrap", StubContext()) is None
