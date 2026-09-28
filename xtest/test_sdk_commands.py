"""Characterization tests for the SDK command builders.

``SubprocessCliAdapter.encrypt_command`` / ``.decrypt_command`` are the single
definition of the ``XT_WITH_*`` contract: ``SDK.encrypt``/``SDK.decrypt`` and
the benchmark harness build their invocations through them. Pinning the argv
and env here means a change to that contract shows up as a failing assertion
rather than as a benchmark silently measuring a different operation than the
functional suite.

Since DSPX-4791 these also carry a second job. The adapter package exists so
the three ``cli.sh`` shims can be replaced by per-SDK argv builders in Python,
and the only thing that makes such a replacement reviewable is a suite that
pins the *current* bytes. Every assertion below was written against the
pre-adapter implementation and is reproduced unchanged; only the call shape
moved. A native adapter that produces a different argv has to change one of
these lines, in a diff where that is the entire point.

``TestSdkDelegation`` covers the one place the two layers genuinely differ:
``ztdf-ecwrap`` is this suite's vocabulary, not the adapter's, so ``tdfs.SDK``
splits it into a container and a wrapping-key flag on the way through.

No platform and no real SDK -- the builders only need ``cli.sh`` to exist, so
these run against a stub tree in ``tmp_path``.
"""

from pathlib import Path

import pytest
from otdf_adapter import DecryptRequest, EncryptRequest, SubprocessCliAdapter

import tdfs


@pytest.fixture
def stub_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A ``sdk/go/dist/main/cli.sh`` that exists and is never executed."""
    cli = tmp_path / "sdk" / "go" / "dist" / "main" / "cli.sh"
    cli.parent.mkdir(parents=True)
    cli.write_text("#!/bin/sh\nexit 0\n")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def adapter(stub_tree: Path) -> SubprocessCliAdapter:
    return SubprocessCliAdapter("go", "main")


@pytest.fixture
def sdk(stub_tree: Path) -> tdfs.SDK:
    """The suite-facing wrapper, over the same stub."""
    return tdfs.SDK("go", "main")


def encrypt(dst: str = "out.tdf", **kwargs: object) -> EncryptRequest:
    return EncryptRequest(src=Path("in.txt"), dst=Path(dst), **kwargs)  # type: ignore[arg-type]


def decrypt(dst: str = "out.txt", **kwargs: object) -> DecryptRequest:
    return DecryptRequest(src=Path("in.tdf"), dst=Path(dst), **kwargs)  # type: ignore[arg-type]


class TestEncryptCommand:
    def test_positional_arguments(self, adapter: SubprocessCliAdapter):
        argv, _ = adapter.encrypt_command(encrypt())
        assert argv == [adapter.path, "encrypt", "in.txt", "out.tdf", "ztdf"]

    def test_mime_type_defaults_on(self, adapter: SubprocessCliAdapter):
        _, env = adapter.encrypt_command(encrypt())
        assert env == {"XT_WITH_MIME_TYPE": "application/octet-stream"}

    def test_empty_mime_type_omits_the_variable(self, adapter: SubprocessCliAdapter):
        # ``""`` is what the suite passes to mean "do not send one"; ``None``
        # is what a typed caller would write. Both have to omit it, because
        # the shim's `-n` guard cannot tell them apart and an empty
        # ``--mime-type ''`` is not the same request.
        for empty in ("", None):
            _, env = adapter.encrypt_command(encrypt(mime_type=empty))
            assert "XT_WITH_MIME_TYPE" not in env

    def test_attributes_are_comma_joined(self, adapter: SubprocessCliAdapter):
        _, env = adapter.encrypt_command(
            encrypt(
                attributes=[
                    "https://e.com/attr/a/value/1",
                    "https://e.com/attr/b/value/2",
                ]
            )
        )
        assert env["XT_WITH_ATTRIBUTES"] == (
            "https://e.com/attr/a/value/1,https://e.com/attr/b/value/2"
        )

    def test_empty_attribute_list_omits_the_variable(
        self, adapter: SubprocessCliAdapter
    ):
        _, env = adapter.encrypt_command(encrypt(attributes=[]))
        assert "XT_WITH_ATTRIBUTES" not in env

    def test_assertions(self, adapter: SubprocessCliAdapter):
        _, env = adapter.encrypt_command(encrypt(assertions="[{}]"))
        assert env["XT_WITH_ASSERTIONS"] == "[{}]"

    def test_target_mode(self, adapter: SubprocessCliAdapter):
        _, env = adapter.encrypt_command(encrypt(target_mode="4.3.0"))
        assert env["XT_WITH_TARGET_MODE"] == "4.3.0"

    def test_ecwrap_is_a_flag_not_a_container(self, adapter: SubprocessCliAdapter):
        argv, env = adapter.encrypt_command(encrypt(ecwrap=True))
        assert argv[-1] == "ztdf", "the CLI format argument is the container"
        assert env["XT_WITH_ECWRAP"] == "true"

    def test_target_mode_survives_ecwrap(self, adapter: SubprocessCliAdapter):
        # The XT_WITH_TARGET_MODE guard tests the container, and ecwrap does
        # not change the container, so target mode applies to both.
        _, env = adapter.encrypt_command(encrypt(ecwrap=True, target_mode="4.3.0"))
        assert env["XT_WITH_TARGET_MODE"] == "4.3.0"
        assert env["XT_WITH_ECWRAP"] == "true"


class TestDecryptCommand:
    def test_positional_arguments(self, adapter: SubprocessCliAdapter):
        argv, env = adapter.decrypt_command(decrypt())
        assert argv == [adapter.path, "decrypt", "in.tdf", "out.txt", "ztdf"]
        assert env == {}, "a plain decrypt sets no XT_WITH_* overrides"

    def test_assertion_verification_keys(self, adapter: SubprocessCliAdapter):
        _, env = adapter.decrypt_command(decrypt(assertion_verification_keys="{keys}"))
        assert env["XT_WITH_ASSERTION_VERIFICATION_KEYS"] == "{keys}"

    def test_verify_assertions_only_set_when_disabled(
        self, adapter: SubprocessCliAdapter
    ):
        _, on = adapter.decrypt_command(decrypt())
        _, off = adapter.decrypt_command(decrypt(verify_assertions=False))
        assert "XT_WITH_VERIFY_ASSERTIONS" not in on
        assert off["XT_WITH_VERIFY_ASSERTIONS"] == "false"

    def test_ecwrap_flag(self, adapter: SubprocessCliAdapter):
        _, env = adapter.decrypt_command(decrypt(ecwrap=True))
        assert env["XT_WITH_ECWRAP"] == "true"

    def test_kas_allowlist(self, adapter: SubprocessCliAdapter):
        # NB: the name asserted here is the name the builder has always
        # emitted, and all three shims read XT_WITH_KAS_ALLOW_LIST -- so this
        # option has never reached an SDK. Pinned as-is on purpose: A1 is the
        # behaviour-identical step, and silently starting to pass
        # --kas-allowlist to three SDKs is not that. See
        # otdf_adapter.subprocess_cli.KNOWN_SHIM_MISMATCH.
        _, env = adapter.decrypt_command(
            decrypt(
                kas_allowlist="http://localhost:8080",
                ignore_kas_allowlist=True,
            )
        )
        assert env["XT_WITH_KAS_ALLOWLIST"] == "http://localhost:8080"
        assert env["XT_WITH_IGNORE_KAS_ALLOWLIST"] == "true"


class TestSdkDelegation:
    """``tdfs.SDK`` translates this suite's vocabulary and nothing else."""

    def test_encrypt_matches_the_adapter(
        self, sdk: tdfs.SDK, adapter: SubprocessCliAdapter
    ):
        assert sdk.encrypt_command(Path("in.txt"), Path("out.tdf")) == (
            adapter.encrypt_command(encrypt())
        )

    def test_decrypt_matches_the_adapter(
        self, sdk: tdfs.SDK, adapter: SubprocessCliAdapter
    ):
        assert sdk.decrypt_command(Path("in.tdf"), Path("out.txt")) == (
            adapter.decrypt_command(decrypt())
        )

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

    def test_decrypt_ecwrap_container_maps_to_ztdf(self, sdk: tdfs.SDK):
        argv, _ = sdk.decrypt_command(
            Path("in.tdf"), Path("out.txt"), container="ztdf-ecwrap"
        )
        assert argv[-1] == "ztdf"

    def test_empty_mime_type_omits_the_variable(self, sdk: tdfs.SDK):
        _, env = sdk.encrypt_command(Path("in.txt"), Path("out.tdf"), mime_type="")
        assert "XT_WITH_MIME_TYPE" not in env

    def test_empty_attribute_list_omits_the_variable(self, sdk: tdfs.SDK):
        _, env = sdk.encrypt_command(Path("in.txt"), Path("out.tdf"), attr_values=[])
        assert "XT_WITH_ATTRIBUTES" not in env

    def test_path_is_the_shim(self, sdk: tdfs.SDK, adapter: SubprocessCliAdapter):
        # conftest and the benchmark harness both read SDK.path directly, and
        # the shim's location is still a bare relative path resolved against
        # the working directory. Killing that coupling is a follow-up.
        assert sdk.path == adapter.path == "sdk/go/dist/main/cli.sh"


class TestDeterminism:
    def test_builders_are_pure(self, adapter: SubprocessCliAdapter):
        # The benchmark builds a command once and runs it many times; a
        # builder that mutated shared state would make round N differ from
        # round 1 and show up as a phantom regression.
        request = encrypt(ecwrap=True, attributes=["a"])
        first = adapter.encrypt_command(request)
        second = adapter.encrypt_command(request)
        assert first == second

    def test_a_caller_owned_list_cannot_change_a_built_command(
        self, adapter: SubprocessCliAdapter
    ):
        # The same hazard one level up: callers pass ``attr_values=[...]``,
        # and a request that stored the caller's list would let a later
        # mutation change what an already-built command runs.
        attrs = ["a"]
        _, before = adapter.encrypt_command(encrypt(attributes=attrs))
        attrs.append("b")
        _, after = adapter.encrypt_command(encrypt(attributes=("a",)))
        assert before == after

    def test_no_side_effects_on_the_filesystem(
        self, adapter: SubprocessCliAdapter, sdk: tdfs.SDK, tmp_path: Path
    ):
        adapter.encrypt_command(encrypt())
        adapter.decrypt_command(decrypt())
        sdk.encrypt_command(Path("in.txt"), Path("out.tdf"))
        sdk.decrypt_command(Path("in.tdf"), Path("out.txt"))
        assert not (tmp_path / "out.tdf").exists()
        assert not (tmp_path / "out.txt").exists()
