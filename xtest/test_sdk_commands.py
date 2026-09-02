"""Unit tests for the SDK CLI command builders in ``tdfs.py``.

``SDK.encrypt_command`` / ``SDK.decrypt_command`` are the single definition of
the ``XT_WITH_*`` contract: both ``SDK.encrypt``/``SDK.decrypt`` and the
benchmark harness build their invocations through them. Pinning the argv and
env here means a change to that contract shows up as a failing assertion
rather than as a benchmark silently measuring a different operation than the
functional suite.

No platform and no real SDK -- the builders only need ``cli.sh`` to exist, so
these run against a stub tree in ``tmp_path``.
"""

from pathlib import Path

import pytest

import tdfs


@pytest.fixture
def sdk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tdfs.SDK:
    """An SDK pointing at a stub ``cli.sh`` that is never executed."""
    cli = tmp_path / "sdk" / "go" / "dist" / "main" / "cli.sh"
    cli.parent.mkdir(parents=True)
    cli.write_text("#!/bin/sh\nexit 0\n")
    monkeypatch.chdir(tmp_path)
    return tdfs.SDK("go", "main")


class TestEncryptCommand:
    def test_positional_arguments(self, sdk: tdfs.SDK):
        argv, _ = sdk.encrypt_command(Path("in.txt"), Path("out.tdf"))
        assert argv == [sdk.path, "encrypt", "in.txt", "out.tdf", "ztdf"]

    def test_mime_type_defaults_on(self, sdk: tdfs.SDK):
        _, env = sdk.encrypt_command(Path("in.txt"), Path("out.tdf"))
        assert env == {"XT_WITH_MIME_TYPE": "application/octet-stream"}

    def test_empty_mime_type_omits_the_variable(self, sdk: tdfs.SDK):
        _, env = sdk.encrypt_command(Path("in.txt"), Path("out.tdf"), mime_type="")
        assert "XT_WITH_MIME_TYPE" not in env

    def test_attributes_are_comma_joined(self, sdk: tdfs.SDK):
        _, env = sdk.encrypt_command(
            Path("in.txt"),
            Path("out.tdf"),
            attr_values=[
                "https://e.com/attr/a/value/1",
                "https://e.com/attr/b/value/2",
            ],
        )
        assert env["XT_WITH_ATTRIBUTES"] == (
            "https://e.com/attr/a/value/1,https://e.com/attr/b/value/2"
        )

    def test_empty_attribute_list_omits_the_variable(self, sdk: tdfs.SDK):
        _, env = sdk.encrypt_command(Path("in.txt"), Path("out.tdf"), attr_values=[])
        assert "XT_WITH_ATTRIBUTES" not in env

    def test_assertions(self, sdk: tdfs.SDK):
        _, env = sdk.encrypt_command(
            Path("in.txt"), Path("out.tdf"), assert_value="[{}]"
        )
        assert env["XT_WITH_ASSERTIONS"] == "[{}]"

    def test_target_mode(self, sdk: tdfs.SDK):
        _, env = sdk.encrypt_command(
            Path("in.txt"), Path("out.tdf"), target_mode="4.3.0"
        )
        assert env["XT_WITH_TARGET_MODE"] == "4.3.0"

    def test_ecwrap_container_maps_to_ztdf_plus_a_flag(self, sdk: tdfs.SDK):
        argv, env = sdk.encrypt_command(
            Path("in.txt"), Path("out.tdf"), container="ztdf-ecwrap"
        )
        assert argv[-1] == "ztdf", "the CLI format argument is the simple container"
        assert env["XT_WITH_ECWRAP"] == "true"

    def test_target_mode_survives_ecwrap(self, sdk: tdfs.SDK):
        # The XT_WITH_TARGET_MODE guard tests the *simplified* format, and
        # ztdf-ecwrap simplifies to ztdf, so target mode applies to both.
        _, env = sdk.encrypt_command(
            Path("in.txt"),
            Path("out.tdf"),
            container="ztdf-ecwrap",
            target_mode="4.3.0",
        )
        assert env["XT_WITH_TARGET_MODE"] == "4.3.0"
        assert env["XT_WITH_ECWRAP"] == "true"


class TestDecryptCommand:
    def test_positional_arguments(self, sdk: tdfs.SDK):
        argv, env = sdk.decrypt_command(Path("in.tdf"), Path("out.txt"))
        assert argv == [sdk.path, "decrypt", "in.tdf", "out.txt", "ztdf"]
        assert env == {}, "a plain decrypt sets no XT_WITH_* overrides"

    def test_assertion_verification_keys(self, sdk: tdfs.SDK):
        _, env = sdk.decrypt_command(
            Path("in.tdf"), Path("out.txt"), assert_keys="{keys}"
        )
        assert env["XT_WITH_ASSERTION_VERIFICATION_KEYS"] == "{keys}"

    def test_verify_assertions_only_set_when_disabled(self, sdk: tdfs.SDK):
        _, on = sdk.decrypt_command(Path("in.tdf"), Path("out.txt"))
        _, off = sdk.decrypt_command(
            Path("in.tdf"), Path("out.txt"), verify_assertions=False
        )
        assert "XT_WITH_VERIFY_ASSERTIONS" not in on
        assert off["XT_WITH_VERIFY_ASSERTIONS"] == "false"

    def test_ecwrap_flag(self, sdk: tdfs.SDK):
        _, env = sdk.decrypt_command(Path("in.tdf"), Path("out.txt"), ecwrap=True)
        assert env["XT_WITH_ECWRAP"] == "true"

    def test_kas_allowlist(self, sdk: tdfs.SDK):
        _, env = sdk.decrypt_command(
            Path("in.tdf"),
            Path("out.txt"),
            kasallowlist="http://localhost:8080",
            ignore_kas_allowlist=True,
        )
        assert env["XT_WITH_KAS_ALLOWLIST"] == "http://localhost:8080"
        assert env["XT_WITH_IGNORE_KAS_ALLOWLIST"] == "true"

    def test_ecwrap_container_maps_to_ztdf(self, sdk: tdfs.SDK):
        argv, _ = sdk.decrypt_command(
            Path("in.tdf"), Path("out.txt"), container="ztdf-ecwrap"
        )
        assert argv[-1] == "ztdf"


class TestDeterminism:
    def test_builders_are_pure(self, sdk: tdfs.SDK):
        # The benchmark builds a command once and runs it many times; a
        # builder that mutated shared state would make round N differ from
        # round 1 and show up as a phantom regression.
        args = (Path("in.txt"), Path("out.tdf"))
        kwargs = {"container": "ztdf-ecwrap", "attr_values": ["a"]}
        first = sdk.encrypt_command(*args, **kwargs)
        second = sdk.encrypt_command(*args, **kwargs)
        assert first == second

    def test_no_side_effects_on_the_filesystem(self, sdk: tdfs.SDK, tmp_path: Path):
        sdk.encrypt_command(Path("in.txt"), Path("out.tdf"))
        sdk.decrypt_command(Path("in.tdf"), Path("out.txt"))
        assert not (tmp_path / "out.tdf").exists()
        assert not (tmp_path / "out.txt").exists()
