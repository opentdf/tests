"""The shim adapter's own behaviour.

The argv and ``XT_WITH_*`` contract is pinned in ``xtest/test_sdk_commands.py``
against the suite that has to keep working. What is pinned here is the part
that has no caller yet: reading a version out of three differently-shaped JSON
documents, and consulting a gate table before shelling out.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from otdf_adapter import gates
from otdf_adapter.gates import Always, Unprobeable
from otdf_adapter.protocol import DecryptRequest, EncryptRequest
from otdf_adapter.subprocess_cli import SubprocessCliAdapter, fmt_env


def install(root: Path, sdk: str = "go", version: str = "main", body: str = "exit 0") -> Path:
    dist = root / "sdk" / sdk / "dist" / version
    dist.mkdir(parents=True, exist_ok=True)
    cli = dist / "cli.sh"
    cli.write_text(f"#!/bin/sh\n{body}\n")
    cli.chmod(0o755)
    return dist


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SubprocessCliAdapter:
    install(tmp_path)
    monkeypatch.chdir(tmp_path)
    return SubprocessCliAdapter("go", "main")


class TestConstruction:
    def test_a_missing_install_raises_at_construction(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="SDK executable not found"):
            SubprocessCliAdapter("go", "main", dist_dir=tmp_path / "nope")

    def test_require_executable_off_allows_a_descriptor_only_probe(self, tmp_path: Path):
        adapter = SubprocessCliAdapter("go", "main", dist_dir=tmp_path, require_executable=False)
        assert adapter.descriptor.adapter == "go"

    def test_str_is_the_spec_the_suite_prints(self, adapter: SubprocessCliAdapter):
        assert str(adapter) == "go@main"


class TestVersion:
    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            ('{"sdk_version":"0.12.0"}', "0.12.0"),
            ('{"version":"0.18.0"}', "0.18.0"),
            ('{"@opentdf/sdk":"0.20.1"}', "0.20.1"),
        ],
    )
    def test_three_sdks_three_keys_one_method(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str, expected: str
    ):
        # The shims spell this as a `jq` pipe repeated in every case arm --
        # `.sdk_version`, `.version`, `.["@opentdf/sdk"]` -- so a version gate
        # cannot be added without also re-deciding how to read a version.
        install(tmp_path, body=f"echo '{payload}'")
        monkeypatch.chdir(tmp_path)
        assert SubprocessCliAdapter("go", "main").version().sdk == expected

    def test_schema_version_is_read_separately(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        install(tmp_path, body='echo \'{"sdk_version":"0.3.0","schema_version":"4.3.0"}\'')
        monkeypatch.chdir(tmp_path)
        v = SubprocessCliAdapter("go", "main").version()
        assert (v.sdk, v.schema) == ("0.3.0", "4.3.0")

    def test_supported_features_are_captured(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        install(tmp_path, body='echo \'{"supported_features":["dpop"]}\'')
        monkeypatch.chdir(tmp_path)
        assert SubprocessCliAdapter("go", "main").version().features == ("dpop",)

    def test_unparseable_output_is_not_an_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # Branch builds print all sorts of things. A version probe that raised
        # would turn a skippable cell into a collection error.
        install(tmp_path, body="echo not-json")
        monkeypatch.chdir(tmp_path)
        v = SubprocessCliAdapter("go", "main").version()
        assert v.raw == "not-json"
        assert v.sdk is None

    def test_it_is_memoized(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        # java pays 150-500 ms of JVM startup per probe; its shim grew a help
        # cache for exactly this reason.
        counter = tmp_path / "calls"
        install(tmp_path, body=f"echo x >> {counter}; echo '{{}}'")
        monkeypatch.chdir(tmp_path)
        adapter = SubprocessCliAdapter("go", "main")
        adapter.version()
        adapter.version()
        assert counter.read_text().count("x") == 1

    def test_help_text_is_memoized_per_subcommand(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        install(tmp_path, body='echo "help for $2"')
        monkeypatch.chdir(tmp_path)
        adapter = SubprocessCliAdapter("go", "main")
        assert adapter.help_text("decrypt").strip() == "help for decrypt"
        assert adapter.help_text("encrypt").strip() == "help for encrypt"
        assert adapter.help_text().strip() == "help for"


class TestSupports:
    def test_it_falls_back_to_the_shim(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        install(tmp_path, body='[ "$2" = "ecwrap" ]')
        monkeypatch.chdir(tmp_path)
        adapter = SubprocessCliAdapter("go", "main")
        assert adapter.supports("ecwrap")
        assert not adapter.supports("hexless")

    def test_an_empty_table_means_today_s_behaviour(self, adapter: SubprocessCliAdapter):
        # The strangler property: no table row means the shim answers, so the
        # tables can be filled one row at a time.
        assert adapter.gate_result("ecwrap") is None

    def test_a_table_row_short_circuits_the_shim(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        install(tmp_path, body="exit 1")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setitem(gates.GATES, "go", {"autoconfigure": Always(True, "always has")})
        adapter = SubprocessCliAdapter("go", "main")
        assert adapter.supports("autoconfigure")
        assert not adapter.supports("ecwrap"), "unlisted features still ask the shim"

    def test_unprobeable_answers_no(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        install(tmp_path, body="exit 0")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setitem(gates.GATES, "go", {"x": Unprobeable("no CLI surface")})
        assert not SubprocessCliAdapter("go", "main").supports("x")

    def test_container_is_accepted_and_does_not_yet_change_the_answer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # `supports` takes a container because capability is per-container --
        # nano has no assertions, ztdf has no ecdsa binding. The shim has
        # nowhere to put the argument, so the answer is the same for both
        # today; the signature is why adding a per-container gate later will
        # not mean touching every caller a second time.
        install(tmp_path, body='[ "$2" = "ecwrap" ]')
        monkeypatch.chdir(tmp_path)
        adapter = SubprocessCliAdapter("go", "main")
        assert adapter.supports("ecwrap", container="ztdf")
        assert adapter.supports("ecwrap", container="nano")


class TestExecution:
    def test_encrypt_returns_its_destination(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        install(tmp_path, body='cp "$2" "$3"')
        monkeypatch.chdir(tmp_path)
        (tmp_path / "in.txt").write_text("hello")
        dst = tmp_path / "out.tdf"
        adapter = SubprocessCliAdapter("go", "main")
        assert adapter.encrypt(EncryptRequest(src=tmp_path / "in.txt", dst=dst)) == dst
        assert dst.read_text() == "hello"

    def test_a_failing_shim_raises_calledprocesserror(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        import subprocess

        install(tmp_path, body="exit 3")
        monkeypatch.chdir(tmp_path)
        adapter = SubprocessCliAdapter("go", "main")
        with pytest.raises(subprocess.CalledProcessError):
            adapter.decrypt(DecryptRequest(src=tmp_path / "a", dst=tmp_path / "b"))

    def test_overrides_are_merged_over_the_environment_not_replacing_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # The shims source test.env and read PLATFORMURL/CLIENTID from the
        # inherited environment; handing them only the overrides would break
        # every invocation.
        install(tmp_path, body='printf "%s|%s" "$PLATFORMURL" "$XT_WITH_MIME_TYPE" > out')
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PLATFORMURL", "http://localhost:8080")
        adapter = SubprocessCliAdapter("go", "main")
        adapter.encrypt(EncryptRequest(src=tmp_path / "in", dst=tmp_path / "o"))
        assert (tmp_path / "out").read_text() == ("http://localhost:8080|application/octet-stream")


def test_fmt_env_renders_shell_assignments():
    assert fmt_env({"A": "1", "B": "x y"}) == "A='1' B='x y'"
