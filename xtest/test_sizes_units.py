"""Offline tests for the payload-size vocabulary and selection machinery (DSPX-4592)."""

import argparse
import warnings
from pathlib import Path
from typing import cast

import pytest

import conftest
import sizes


class TestSizes:
    def test_medium_is_inside_the_broken_window(self):
        """The whole ticket rests on this one number being in the band."""
        assert sizes.in_zip64_window(sizes.MEDIUM_BYTES)

    def test_medium_has_margin_below_the_low_edge(self):
        """Manifest size and segment padding must not push the offset back under 2**31.

        The manifest is written after the payload, so its local-header offset
        is the payload size plus header overhead -- but the assertion that
        matters is the reverse: the payload alone must already clear the
        boundary by more than any plausible overhead.
        """
        margin = sizes.MEDIUM_BYTES - sizes.ZIP64_WINDOW_LOW
        assert margin > 100 * 2**20, (
            f"only {margin} bytes of margin above 2**31; segment padding and "
            "manifest size could push the interesting offset back below it"
        )

    def test_small_and_large_sit_outside_the_window(self):
        """The two pre-existing sizes are exactly why this ticket exists."""
        assert sizes.SIZES["small"] < sizes.ZIP64_WINDOW_LOW
        assert sizes.SIZES["large"] >= sizes.ZIP64_WINDOW_HIGH
        assert not sizes.in_zip64_window(sizes.SIZES["small"])
        assert not sizes.in_zip64_window(sizes.SIZES["large"])

    # Named size_name, not size: `size` is parametrized session-wide by
    # conftest's pytest_generate_tests, and reusing it here is a collection
    # error rather than a shadow.
    @pytest.mark.parametrize(
        ("size_name", "expected"),
        [("small", False), ("chunky", False), ("medium", True), ("large", True)],
    )
    def test_which_sizes_select_the_zip64_tests(self, size_name: str, expected: bool):
        assert sizes.exercises_zip64_window(size_name) is expected

    def test_chunky_clears_every_sdk_default_segment(self):
        """5 MiB has to buy more than one *default-sized* segment, everywhere.

        Segment defaults observed in the live 2.1 GiB run: web-sdk 1 MiB, go
        and java ~2 MiB. Two full default segments from the largest of those
        is 4 MiB, so anything at or below that tests nothing for go and java.
        The runtime counterpart is the ``len(segments) > 1`` assertion in
        test_tdfs.py::test_chunky_roundtrip, which catches a default this
        constant has not been told about.
        """
        largest_known_default = 2 * 2**20
        assert sizes.CHUNKY_BYTES > 2 * largest_known_default

    def test_chunky_stays_cheap(self):
        """It runs on the PR gate, so it must not creep toward the nightly's cost."""
        assert sizes.CHUNKY_BYTES < 64 * 2**20
        assert not sizes.in_zip64_window(sizes.CHUNKY_BYTES)


class TestSizesOptionParsing:
    def test_dedups_and_orders_cheapest_first(self):
        assert conftest.sizes_opt_type("large,small,small") == ["small", "large"]

    def test_single_name(self):
        assert conftest.sizes_opt_type("large") == ["large"]

    def test_unknown_name_raises(self):
        with pytest.raises(argparse.ArgumentTypeError, match="unknown size"):
            conftest.sizes_opt_type("bogus")

    def test_empty_string_raises(self):
        with pytest.raises(argparse.ArgumentTypeError, match="at least one size"):
            conftest.sizes_opt_type("")


class _FakeConfig:
    """Just enough of ``pytest.Config`` for ``resolve_sizes``."""

    def __init__(self, sizes_opt: list[str] | None, large_opt: bool):
        self.stash = pytest.Stash()
        self._options = {"--sizes": sizes_opt, "--large": large_opt}

    def getoption(self, name: str):
        return self._options[name]


class TestResolveSizes:
    def test_sizes_option_passes_through(self):
        config = cast(pytest.Config, _FakeConfig(["small", "large"], False))
        assert conftest.resolve_sizes(config) == ["small", "large"]

    def test_no_options_defaults_to_small(self):
        config = cast(pytest.Config, _FakeConfig(None, False))
        assert conftest.resolve_sizes(config) == ["small"]

    def test_large_resolves_to_small_and_large_with_warning(self):
        config = cast(pytest.Config, _FakeConfig(None, True))
        with pytest.warns(DeprecationWarning):
            assert conftest.resolve_sizes(config) == ["small", "large"]

    def test_large_and_sizes_together_is_a_usage_error(self):
        config = cast(pytest.Config, _FakeConfig(["small"], True))
        with pytest.raises(pytest.UsageError, match="mutually exclusive"):
            conftest.resolve_sizes(config)

    def test_result_is_cached_on_the_config(self):
        """The deprecation warning fires once per session, not once per caller."""
        config = cast(pytest.Config, _FakeConfig(None, True))
        with pytest.warns(DeprecationWarning):
            first = conftest.resolve_sizes(config)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            second = conftest.resolve_sizes(config)
        assert first == second == ["small", "large"]


class TestBulkPlaintext:
    def test_partial_final_block_has_the_exact_requested_length(self, tmp_path: Path):
        """MEDIUM_BYTES is not a multiple of _BULK_BLOCK; this is the path that hits."""
        length = 2 * conftest._BULK_BLOCK + 123
        p = tmp_path / "plain.bin"
        conftest._write_bulk_plaintext(p, length)
        assert p.stat().st_size == length

    def test_generation_is_deterministic(self, tmp_path: Path):
        length = 2 * conftest._BULK_BLOCK + 123
        first = tmp_path / "a.bin"
        second = tmp_path / "b.bin"
        conftest._write_bulk_plaintext(first, length)
        conftest._write_bulk_plaintext(second, length)
        assert first.read_bytes() == second.read_bytes()
