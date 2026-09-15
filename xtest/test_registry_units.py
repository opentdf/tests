"""Offline tests for the entry-point registries (DSPX-4794).

Two jobs.

**Pin today's extension-point surface.** ``registry.py`` deliberately does not
import ``tdfs`` -- that acyclicity is what lets ``tdfs`` import it -- so the
built-in name lists exist twice. The pin tests are the only thing keeping the
copies honest, and they double as the record of what the closed sets contained
before any of this: a future widening has to edit a test that spells out
today's values.

**Prove the seam actually works.** The acceptance gate for this ticket is a
throwaway out-of-tree plugin being discovered without touching the xtest source
tree. ``_install_plugin`` therefore builds a real ``.dist-info`` on ``sys.path``
and lets ``importlib.metadata`` find it. Monkeypatching ``registry.CONTAINERS``
would pass while proving nothing about the mechanism consumers would actually
use.

No platform, no SDK, no subprocess.
"""

import importlib
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any, get_args

import pytest

import registry
import tdfs


@pytest.fixture(autouse=True)
def _clean_registries() -> Iterator[None]:
    """Isolate registry and forced-feature mutations from the rest of the run."""
    saved_sdks = (registry.SDKS._entries.copy(), registry.SDKS._loaded)
    saved_containers = (
        registry.CONTAINERS._entries.copy(),
        registry.CONTAINERS._loaded,
    )
    saved_installers = (
        registry.INSTALLERS._entries.copy(),
        registry.INSTALLERS._loaded,
    )
    saved_forced_supports = tdfs._forced_supports
    registry.reset_all()
    try:
        yield
    finally:
        registry.SDKS._entries, registry.SDKS._loaded = saved_sdks
        registry.CONTAINERS._entries, registry.CONTAINERS._loaded = saved_containers
        registry.INSTALLERS._entries, registry.INSTALLERS._loaded = saved_installers
        tdfs._forced_supports = saved_forced_supports


# --- the pin -------------------------------------------------------------------


class TestBuiltinsMatchTheLiterals:
    """The duplication in ``registry.py`` cannot be allowed to drift.

    Each assertion here is also the written-down form of one closed set, so
    widening it is visible in a diff rather than implicit in a Literal edit.
    """

    def test_sdks(self):
        assert registry.BUILTIN_SDKS == get_args(tdfs.sdk_type)
        assert registry.BUILTIN_SDKS == ("go", "java", "js")

    def test_containers(self):
        assert registry.BUILTIN_CONTAINERS == get_args(tdfs.container_type)
        assert registry.BUILTIN_CONTAINERS == ("ztdf", "ztdf-ecwrap")

    def test_features(self):
        assert registry.BUILTIN_FEATURES == get_args(tdfs.feature_type)

    def test_focus_is_derived_and_needs_no_registry_of_its_own(self):
        """``focus_type`` is ``Literal[sdk_type, "all"]``, so it widens for free."""
        assert set(get_args(tdfs.focus_type)) == set(registry.BUILTIN_SDKS) | {"all"}

    def test_group_names(self):
        assert registry.GROUP_ADAPTERS == "otdf.adapters"
        assert registry.GROUP_CONTAINERS == "otdf.containers"
        assert registry.GROUP_INSTALLERS == "otdf.installers"


# --- registry mechanics --------------------------------------------------------


class _FakeContainer:
    """An in-process stand-in, for the mechanics that do not need a real dist."""

    name = "acme"
    wire_format = "acme"
    features = frozenset({"acme-sealed"})

    def inspect(self, path: Path) -> registry.Inspection:
        raise NotImplementedError

    def tamper(self, path: Path, mutation: registry.Mutation) -> Path:
        raise registry.UnsupportedMutation(mutation)

    def requires_attributes(self) -> bool:
        return True


class TestRegistry:
    def test_builtins_are_registered_before_any_discovery(self):
        assert registry.container_names() == ("ztdf", "ztdf-ecwrap")
        assert registry.sdk_names() == ("go", "java", "js")

    def test_a_builtin_without_an_implementation_is_still_a_known_name(self):
        """What makes this module landable ahead of the adapters.

        The parametrizers and validators need the *names*; the objects arrive
        with the container-adapter change.
        """
        assert "ztdf" in registry.CONTAINERS
        with pytest.raises(registry.UnknownName, match="no implementation yet"):
            registry.CONTAINERS.get("ztdf")

    def test_unknown_name_lists_the_alternatives(self):
        with pytest.raises(registry.UnknownName) as e:
            registry.CONTAINERS.get("ztfd")
        assert "ztdf" in str(e.value)
        assert "ztdf-ecwrap" in str(e.value)

    def test_a_plugin_may_not_shadow_a_builtin(self):
        """Silent override would make --containers ztdf mean whatever is installed."""
        with pytest.raises(registry.DuplicateName):
            registry.CONTAINERS.register("ztdf", _FakeContainer())

    def test_two_plugins_may_not_share_a_name(self):
        registry.CONTAINERS.register("acme", _FakeContainer())
        with pytest.raises(registry.DuplicateName):
            registry.CONTAINERS.register("acme", _FakeContainer())

    def test_load_is_idempotent(self):
        """Each xdist worker configures itself; a second scan must not re-register."""
        registry.load_all()
        before = registry.container_names()
        registry.load_all()
        assert registry.container_names() == before

    def test_feature_names_start_as_the_builtins(self):
        assert registry.feature_names() == frozenset(registry.BUILTIN_FEATURES)

    def test_feature_names_pick_up_a_plugins_declaration(self):
        registry.CONTAINERS.register("acme", _FakeContainer())
        assert "acme-sealed" in registry.feature_names()
        assert frozenset(registry.BUILTIN_FEATURES) <= registry.feature_names()


# --- the acceptance gate: a real out-of-tree distribution -----------------------


_PLUGIN_SOURCE = textwrap.dedent(
    '''
    """A throwaway out-of-tree plugin. Knows nothing about xtest's internals."""

    from dataclasses import dataclass


    @dataclass
    class Container:
        name: str = "acme"
        wire_format: str = "acme"
        features: frozenset = frozenset({"acme-sealed"})

        def inspect(self, path):
            raise NotImplementedError

        def tamper(self, path, mutation):
            raise NotImplementedError

        def requires_attributes(self):
            return True


    @dataclass
    class Sdk:
        name: str = "acme"
        features: frozenset = frozenset({"acme-dialect"})

        def versions(self):
            return ("v1.0.0",)


    CONTAINER = Container()
    SDK = Sdk()
    MISNAMED_CONTAINER = Container(name="not-acme")
    BROKEN = None
    '''
)


def _install_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry_points_txt: str
) -> None:
    """Put a real installed distribution on ``sys.path``.

    A ``.dist-info`` directory with ``METADATA`` and ``entry_points.txt`` is
    all ``importlib.metadata`` needs, so this exercises the same discovery
    path a ``uv pip install`` would produce -- without building a wheel or
    touching the environment the test session itself runs in.
    """
    site = tmp_path / "site"
    (site / "acme_xtest").mkdir(parents=True)
    (site / "acme_xtest" / "__init__.py").write_text(_PLUGIN_SOURCE)
    dist = site / "acme_xtest-0.1.0.dist-info"
    dist.mkdir()
    dist.joinpath("METADATA").write_text(
        "Metadata-Version: 2.1\nName: acme-xtest\nVersion: 0.1.0\n"
    )
    dist.joinpath("entry_points.txt").write_text(entry_points_txt)

    monkeypatch.syspath_prepend(str(site))
    importlib.invalidate_caches()
    monkeypatch.delitem(sys.modules, "acme_xtest", raising=False)


@pytest.fixture
def plugin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_plugin(
        tmp_path,
        monkeypatch,
        "[otdf.containers]\n"
        "acme = acme_xtest:CONTAINER\n"
        "\n"
        "[otdf.adapters]\n"
        "acme = acme_xtest:SDK\n",
    )


@pytest.mark.usefixtures("plugin")
class TestOutOfTreePlugin:
    """DSPX-4794's acceptance gate."""

    def test_a_container_is_discovered_without_touching_xtest(self):
        registry.load_all()
        assert "acme" in registry.container_names()
        assert registry.CONTAINERS.get("acme").wire_format == "acme"

    def test_an_sdk_is_discovered_without_touching_xtest(self):
        registry.load_all()
        assert "acme" in registry.sdk_names()
        assert registry.SDKS.get("acme").versions() == ("v1.0.0",)

    def test_builtins_survive_the_widening(self):
        registry.load_all()
        assert set(registry.BUILTIN_CONTAINERS) < set(registry.container_names())
        assert set(registry.BUILTIN_SDKS) < set(registry.sdk_names())

    def test_the_plugins_features_join_the_known_set(self):
        registry.load_all()
        assert {"acme-sealed", "acme-dialect"} <= registry.feature_names()

    def test_force_supports_accepts_a_feature_the_plugin_contributed(self):
        """The ordering and the registry, end to end: discovery has to happen
        before the parse for a plugin's feature name to be forceable at all.
        """
        registry.load_all()
        assert tdfs.configure_forced_supports("acme-sealed") == frozenset(
            {"acme-sealed"}
        )

    def test_force_supports_still_rejects_a_typo(self):
        """A validator that accepts everything is the failure mode it exists to stop."""
        registry.load_all()
        with pytest.raises(ValueError, match="unknown feature"):
            tdfs.configure_forced_supports("acme-seeled")

    def test_a_container_adapter_declares_itself_attribute_requiring(self):
        """A format with no no-attribute roundtrip has to be able to say so.

        xtest's default cell encrypts with no attributes; today that is
        unrepresentable as anything but a confusing CLI usage failure.
        """
        registry.load_all()
        assert registry.CONTAINERS.get("acme").requires_attributes() is True


class TestPluginFailuresAreLoud:
    def test_an_entry_point_that_cannot_be_imported_fails_the_session(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Never a ``continue``.

        ``entry_points()`` only reads metadata, so a broken plugin surfaces at
        ``ep.load()``. Swallowing it yields a run that quietly tests less than
        it was asked to, with nothing non-zero anywhere: the missing container
        simply produces fewer cells.
        """
        _install_plugin(
            tmp_path,
            monkeypatch,
            "[otdf.containers]\nacme = acme_xtest_typo:CONTAINER\n",
        )
        with pytest.raises(registry.PluginLoadError) as e:
            registry.load_all()
        assert "otdf.containers" in str(e.value)
        assert "acme" in str(e.value)

    def test_a_plugin_claiming_a_builtin_name_fails_the_session(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        _install_plugin(
            tmp_path,
            monkeypatch,
            "[otdf.containers]\nztdf = acme_xtest:CONTAINER\n",
        )
        with pytest.raises(registry.DuplicateName):
            registry.load_all()

    @pytest.mark.parametrize(
        ("group", "target", "contract"),
        [
            ("otdf.containers", "BROKEN", "ContainerAdapter"),
            ("otdf.containers", "SDK", "ContainerAdapter"),
            ("otdf.adapters", "CONTAINER", "SdkProvider"),
            ("otdf.installers", "SDK", "Installer"),
        ],
    )
    def test_a_plugin_object_must_match_its_groups_contract(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        group: str,
        target: str,
        contract: str,
    ):
        _install_plugin(
            tmp_path,
            monkeypatch,
            f"[{group}]\nacme = acme_xtest:{target}\n",
        )
        with pytest.raises(registry.PluginLoadError, match=contract):
            registry.load_all()

    def test_a_plugin_object_name_must_match_the_entry_point(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        _install_plugin(
            tmp_path,
            monkeypatch,
            "[otdf.containers]\nacme = acme_xtest:MISNAMED_CONTAINER\n",
        )
        with pytest.raises(registry.PluginLoadError, match="name is 'not-acme'"):
            registry.load_all()


# --- the shapes the container seam will be built on ----------------------------


class TestContractShapes:
    def test_inspection_covers_every_assertion_test_tdfs_makes_after_encrypt(self):
        """``test_tdfs.py:70-77`` reads a ZIP one line after encrypt.

        Those assertions -- payload encrypted, exactly one KAO, the KAO's
        wrap type, and an ephemeral public key for ecwrap -- have to survive
        the move behind ``ContainerAdapter.inspect``, or the seam is not a
        drop-in.
        """
        i = registry.Inspection(
            container="ztdf",
            total_size=1024,
            ciphertext_size=128,
            encrypted=True,
            key_access_mode="ec-wrapped",
            key_access=(
                registry.KeyAccessRecord(
                    kas_url="http://localhost:8080/kas", has_ephemeral_key=True
                ),
            ),
        )
        assert i.encrypted
        assert len(i.key_access) == 1
        assert i.key_access_mode == "ec-wrapped"
        assert i.key_access[0].has_ephemeral_key

    def test_raw_is_untyped_on_purpose(self):
        """A typed escape hatch would quietly re-close the seam."""
        assert registry.Inspection.__annotations__["raw"] in ("object", object)

    def test_the_mutation_vocabulary_covers_todays_tamper_tests(self):
        """Ten names, derived from the 23 in-tree update_manifest/update_payload sites."""
        assert {m.value for m in registry.Mutation} == {
            "unbind_policy",
            "alter_policy_binding",
            "alter_root_signature",
            "forge_gmac_root",
            "alter_segment_hash",
            "alter_segment_size",
            "alter_payload_tail",
            "alter_assertion",
            "malicious_kao",
            "duplicate_kao",
        }

    def test_an_inexpressible_mutation_is_reportable_not_a_crash(self):
        """A container that cannot express a tamper must say so.

        Today a non-ZIP container reaching ``update_manifest`` would raise
        ``BadZipFile`` from three modules away.
        """
        c: Any = _FakeContainer()
        with pytest.raises(registry.UnsupportedMutation):
            c.tamper(Path("x"), registry.Mutation.FORGE_GMAC_ROOT)
