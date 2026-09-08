"""Offline tests for the payload-size vocabulary and selection machinery (DSPX-4592)."""

import argparse
import warnings
from pathlib import Path
from typing import cast

import pytest

import conftest


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
