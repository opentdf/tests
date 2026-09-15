"""Offline tests for conftest's SDK selection (DSPX-4794).

``resolve_sdks`` decides what the encrypt and decrypt axes of the whole matrix
fan out over, and its failure mode is silence: parametrizing over an empty list
does not collect zero items, it collects one *skip* per test and exits 0. So
the interesting assertions here are the ones about emptiness, not the ones
about the happy path.

No platform and no real SDK -- the selector only needs a ``cli.sh`` to exist,
so these run against a stub tree in ``tmp_path``.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import tdfs
from conftest import resolve_sdks


def _config(**options: Any) -> pytest.Config:
    """A stand-in exposing only the ``getoption`` resolve_sdks reads."""
    return cast(
        pytest.Config,
        SimpleNamespace(getoption=lambda name: options.get(name)),
    )


@pytest.fixture
def dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Install stub ``cli.sh`` files into a throwaway ``sdk/`` tree."""

    def install(*specs: str) -> None:
        for spec in specs:
            sdk, version = spec.split("@", 1)
            cli = tmp_path / "sdk" / sdk / "dist" / version / "cli.sh"
            cli.parent.mkdir(parents=True, exist_ok=True)
            cli.write_text("#!/bin/sh\nexit 0\n")

    monkeypatch.chdir(tmp_path)
    return install


class TestDefaultsToInstalled:
    def test_empty_default_is_an_error_not_an_empty_matrix(self):
        """Nothing installed must fail the run, not skip it.

        An empty parametrization collects as "got empty parameter set for
        (encrypt_sdk)" and exits 0 -- a green run that tested nothing.
        """
        with pytest.raises(pytest.UsageError, match="otdf-sdk-mgr install"):
            resolve_sdks(_config(), ["--sdks-encrypt", "--sdks"], "encrypt")

    def test_error_names_the_side_and_the_options(self):
        with pytest.raises(pytest.UsageError) as e:
            resolve_sdks(_config(), ["--sdks-decrypt", "--sdks"], "decrypt")
        assert "decrypt side" in str(e.value)
        assert "--sdks-decrypt / --sdks" in str(e.value)

    def test_default_is_every_installed_build(self, dist: Any):
        dist("go@main", "go@v0.18.0", "js@main")
        got = resolve_sdks(_config(), ["--sdks"], "encrypt")
        assert [str(s) for s in got] == ["go@main", "go@v0.18.0", "js@main"]

    def test_default_ignores_sdks_that_are_known_but_not_installed(self, dist: Any):
        """java is in ``sdk_type`` and absent from disk; it must not be selected."""
        dist("go@main")
        assert [str(s) for s in resolve_sdks(_config(), ["--sdks"], "encrypt")] == [
            "go@main"
        ]

    def test_order_is_stable(self, dist: Any):
        """Parameter ids and bench arm tie-breaks must not depend on readdir order."""
        dist("go@v0.9.0", "go@main", "go@v0.18.0")
        assert [s.version for s in tdfs.all_versions_of("go")] == [
            "main",
            "v0.18.0",
            "v0.9.0",
        ]


class TestExplicitOptions:
    def test_first_matching_option_wins(self, dist: Any):
        dist("go@main", "js@main")
        got = resolve_sdks(
            _config(**{"--sdks-encrypt": "js@main", "--sdks": "go@main"}),
            ["--sdks-encrypt", "--sdks"],
            "encrypt",
        )
        assert [str(s) for s in got] == ["js@main"]

    def test_falls_through_to_the_shared_option(self, dist: Any):
        dist("go@main", "js@main")
        got = resolve_sdks(
            _config(**{"--sdks": "go@main"}), ["--sdks-encrypt", "--sdks"], "encrypt"
        )
        assert [str(s) for s in got] == ["go@main"]

    def test_star_expands_to_every_version_of_that_sdk(self, dist: Any):
        dist("go@main", "go@v0.18.0", "js@main")
        got = resolve_sdks(_config(**{"--sdks": "go@*"}), ["--sdks"], "encrypt")
        assert [str(s) for s in got] == ["go@main", "go@v0.18.0"]

    def test_an_explicit_narrowing_to_nothing_is_left_alone(self, dist: Any):
        """Deliberately *not* an error.

        ``--sdks go`` with no go installed may be a scripted narrowing of a
        larger matrix. The guard is on the default path only, where an empty
        result means the harness was never provisioned.
        """
        dist("js@main")
        assert resolve_sdks(_config(**{"--sdks": "go"}), ["--sdks"], "encrypt") == []

    def test_unknown_sdk_name_is_a_usage_error(self, dist: Any):
        dist("go@main")
        with pytest.raises(pytest.UsageError, match="Unknown SDK type"):
            resolve_sdks(_config(**{"--sdks": "rust"}), ["--sdks"], "encrypt")

    def test_missing_build_is_a_usage_error_not_a_traceback(self, dist: Any):
        dist("go@main")
        with pytest.raises(pytest.UsageError, match="SDK executable not found"):
            resolve_sdks(_config(**{"--sdks": "go@v0.1.0"}), ["--sdks"], "encrypt")


class TestInstalledSdks:
    def test_reports_nothing_when_the_dist_tree_is_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        assert tdfs.installed_sdks() == []

    def test_a_half_installed_build_still_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A dist directory with no ``cli.sh`` is a broken install, not an absence.

        Worth pinning separately: this is the one path that already produced a
        ``FileNotFoundError``, and it must keep doing so rather than being
        swallowed into "nothing installed".
        """
        (tmp_path / "sdk" / "go" / "dist" / "main").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(FileNotFoundError):
            tdfs.installed_sdks()
