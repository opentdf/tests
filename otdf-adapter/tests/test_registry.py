"""Entry-point discovery, and the built-in names it has to keep resolving."""

from __future__ import annotations

from pathlib import Path

import pytest

from otdf_adapter import registry
from otdf_adapter.protocol import SdkAdapter
from otdf_adapter.registry import AdapterNotFoundError, load_adapter, load_factory
from otdf_adapter.subprocess_cli import SubprocessCliAdapter


@pytest.fixture
def installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cli = tmp_path / "sdk" / "go" / "dist" / "v1.2.3" / "cli.sh"
    cli.parent.mkdir(parents=True)
    cli.write_text("#!/bin/sh\nexit 0\n")
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestDiscovery:
    def test_the_built_ins_are_registered_as_entry_points(self):
        # Registered the same way a consumer would register theirs, rather
        # than special-cased -- so the extension path is the path the default
        # run exercises and cannot quietly rot.
        assert {"go", "java", "js"} <= set(registry.available_adapters())

    def test_every_built_in_name_resolves_to_a_factory(self):
        for name in registry.BUILTIN_ADAPTERS:
            assert load_factory(name) is SubprocessCliAdapter

    def test_adapter_names_includes_the_built_ins(self):
        assert set(registry.BUILTIN_ADAPTERS) <= set(registry.adapter_names())

    def test_an_unknown_name_names_the_alternatives(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(registry, "available_adapters", dict)
        with pytest.raises(AdapterNotFoundError) as e:
            load_factory("nosuchsdk")
        assert "go" in str(e.value)

    def test_a_built_in_resolves_without_installed_metadata(self, monkeypatch: pytest.MonkeyPatch):
        # A source checkout on sys.path has no distribution metadata, which is
        # how this suite is run today. Failing to resolve its own built-ins in
        # that case is a confusing way to learn about packaging.
        monkeypatch.setattr(registry, "available_adapters", dict)
        assert load_factory("go") is SubprocessCliAdapter

    def test_an_entry_point_that_is_not_callable_is_rejected(self, monkeypatch: pytest.MonkeyPatch):
        class NotCallable:
            name = "go"

            def load(self) -> object:
                return "a string"

        monkeypatch.setattr(registry, "available_adapters", lambda: {"go": NotCallable()})
        with pytest.raises(AdapterNotFoundError, match="not callable"):
            load_factory("go")


class TestLoadAdapter:
    def test_what_comes_back_satisfies_the_protocol(self, installed: Path):
        # The one check the registry cannot make statically -- the factory
        # came from a distribution it does not import.
        assert isinstance(load_adapter("go", "v1.2.3"), SdkAdapter)

    def test_it_locates_the_install_under_sdk_dir(self, installed: Path):
        # `path` is on SubprocessCliAdapter, not on the protocol: an adapter
        # that links the SDK as a library has no executable to name.
        adapter = load_adapter("go", "v1.2.3")
        assert isinstance(adapter, SubprocessCliAdapter)
        # Relative, deliberately. The suite logs this string on every
        # invocation and runs from the xtest directory, so an absolute path
        # would make both the logs and the golden argv machine-specific.
        assert adapter.path == "sdk/go/dist/v1.2.3/cli.sh"
        assert (installed / adapter.path).is_file()

    def test_an_explicit_dist_dir_wins(self, installed: Path):
        adapter = load_adapter("go", "v1.2.3", dist_dir=installed / "sdk/go/dist/v1.2.3")
        assert isinstance(adapter, SubprocessCliAdapter)
        assert Path(adapter.path).is_file()

    def test_a_missing_install_is_a_file_not_found(self, installed: Path):
        with pytest.raises(FileNotFoundError, match="SDK executable not found"):
            load_adapter("go", "v9.9.9")
