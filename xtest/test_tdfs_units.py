"""Offline tests for tdfs.py's XT_FORCE_SUPPORTS override (DSPX-4638).

No platform, no SDK, no subprocess. ``_parse_forced_supports`` is a safeguard
built specifically to stop a typo'd feature name from silently masquerading
as "not supported" -- so it's worth testing on its own.
"""

import pytest

import tdfs


class TestParseForcedSupports:
    def test_parses_comma_and_whitespace_separated_names(self):
        assert tdfs._parse_forced_supports(" hexless, dpop ,ecwrap") == frozenset(
            {"hexless", "dpop", "ecwrap"}
        )

    def test_empty_string_yields_empty_set(self):
        assert tdfs._parse_forced_supports("") == frozenset()
        assert tdfs._parse_forced_supports("   ") == frozenset()

    def test_unknown_name_raises(self):
        """The whole point of this function: a typo must not be a silent no-op."""
        with pytest.raises(ValueError, match="unknown feature"):
            tdfs._parse_forced_supports("hexles")
