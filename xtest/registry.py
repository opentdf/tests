"""Entry-point registries for SDKs, container formats and feature gates.

xtest is pinned at ``@main`` by four repos -- ``opentdf/platform``,
``web-sdk``, ``java-sdk`` and ``otdfctl`` -- and none of them can extend it.
What the suite is allowed to test is decided by three closed ``Literal``\\ s in
``tdfs.py``: ``sdk_type``, ``container_type`` and ``feature_type``. Adding an
SDK, a container format or a capability gate means editing this repo.

Upstream has already paid for that once. NanoTDF was removed in ``150e3135``
("fix: remove NanoTDF tests and support (#366)") -- 11 files, +22/-2003 -- and
``otdf-sdk-mgr/tests/test_schema.py::test_removed_nano_container_is_rejected``
now exists to keep a *second* hand-maintained copy of the container enum
(``otdf_sdk_mgr.schema.ContainerKind``) in step with the first. A format that
was never more than an enum value cost two thousand lines to remove, because
the value was load-bearing everywhere instead of confined to one object.

This module is the seam. Today's ``Literal`` values stay exactly where they
are, as the built-in defaults; anything installed alongside xtest can add to
them by declaring an entry point.

Keeping static typing useful once the set is open
-------------------------------------------------

The ``Literal``\\ s are not widened to ``str`` and not widened to
``Literal[...] | str`` (pyright collapses that union to ``str`` and silently
stops diagnosing). Four mechanisms replace the one:

1. The ``Literal``\\ s stay authoritative for in-tree code, so a literal typo
   is still a type error and deleting a built-in still breaks every mention of
   it at once.
2. Parameters carrying a *parametrized* value -- whose contents come from
   ``metafunc.parametrize`` over a runtime set -- widen to plain ``str``,
   which is the type they always really had.
3. The typo check for names arriving from outside moves to collection time:
   :meth:`Registry.get` raises :class:`UnknownName` listing every registered
   name, before a single test runs.
4. The built-in tuples below are pinned against ``get_args()`` of the
   corresponding ``Literal`` by ``test_registry_units.py``.

That last one is load-bearing. This module deliberately does **not** import
``tdfs`` -- that is what lets ``tdfs`` import *it* without a cycle -- so the
built-in names are written out twice. Without the pin test, that duplication
is a second ``ContainerKind``, i.e. exactly the defect being removed here. If
the pin test is ever deleted, collapse the duplication in the same change.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

logger = logging.getLogger("xtest")

#: Entry-point group for SDK adapters. An entry registers an SDK name.
GROUP_ADAPTERS = "otdf.adapters"

#: Entry-point group for container-format adapters. An entry registers a
#: container name.
GROUP_CONTAINERS = "otdf.containers"

#: Entry-point group for SDK installers -- how an out-of-tree SDK becomes
#: materialisable under ``sdk/<name>/dist/<version>/``. Reserved here so the
#: three groups are designed together; its consumer is ``otdf-sdk-mgr``, not
#: xtest, and wiring it is a separate change.
GROUP_INSTALLERS = "otdf.installers"

#: Mirrors ``tdfs.sdk_type``. Pinned by ``test_registry_units.py``.
BUILTIN_SDKS: tuple[str, ...] = ("go", "java", "js")

#: Mirrors ``tdfs.container_type``. Pinned by ``test_registry_units.py``.
BUILTIN_CONTAINERS: tuple[str, ...] = ("ztdf", "ztdf-ecwrap")

#: Mirrors ``tdfs.feature_type``. Pinned by ``test_registry_units.py``.
#:
#: Order follows the ``Literal`` so a diff against it reads cleanly. The
#: rationale for each name lives on the ``Literal``; this is a name list, not
#: a second place to document them.
BUILTIN_FEATURES: tuple[str, ...] = (
    "assertions",
    "assertion_verification",
    "attribute_traversal",
    "audit_logging",
    "autoconfigure",
    "better-messages-2024",
    "bulk_rewrap",
    "chunky",
    "connectrpc",
    "dpop",
    "dpop_nonce_challenge",
    "ecwrap",
    "gmac_root_rejected",
    "hexless",
    "hexaflexible",
    "kasallowlist",
    "key_management",
    "mechanism-rsa-4096",
    "mechanism-ec-curves-384-521",
    "mechanism-xwing",
    "mechanism-secpmlkem",
    "mechanism-mlkem",
    "multikao",
    "ns_grants",
    "obligations",
    "zip64-at-2gib",
)


class UnknownName(LookupError):
    """A name that no built-in and no plugin registered."""


class DuplicateName(RuntimeError):
    """Two registrations claimed the same name."""


class PluginLoadError(RuntimeError):
    """An entry point was declared but could not be imported."""


class UnsupportedMutation(NotImplementedError):
    """This container format cannot express the requested tamper."""


# --- what a plugin provides ---------------------------------------------------


@runtime_checkable
class Extension(Protocol):
    """Common surface of anything reachable through one of the groups above.

    ``features`` is how :func:`feature_names` widens: a feature name is
    contributed by the adapter or container that answers to it, rather than
    coming from a fourth entry-point group of its own. That way a feature
    cannot exist with nothing behind it, and ``XT_FORCE_SUPPORTS`` cannot be
    handed a name that nothing will ever report on.
    """

    name: str
    features: frozenset[str]


@dataclass(frozen=True)
class KeyAccessRecord:
    """One key-access object, in terms every container format can answer."""

    kas_url: str
    kid: str | None = None
    split_id: str | None = None
    wrap_algorithm: str | None = None
    has_ephemeral_key: bool = False


@dataclass(frozen=True)
class Inspection:
    """What a test may ask about a container without knowing its encoding.

    Every field is answerable by any format that binds a policy to a wrapped
    key and hands it to a KAS. None presumes a ZIP, a JSON manifest, or a
    named entry -- which is what ``test_tdfs.py`` presumes today when it calls
    ``tdfs.manifest()`` one line after encrypt, inside a test parametrized over
    ``container``.

    ``raw`` is typed ``object`` on purpose. A conveniently typed escape hatch
    would quietly re-close the seam; as it stands, a test that wants the ztdf
    ``Manifest`` has to reach for ``tdfs.manifest()`` and thereby declare
    itself ztdf-only.
    """

    container: str
    total_size: int
    ciphertext_size: int
    encrypted: bool
    key_access_mode: str
    key_access: tuple[KeyAccessRecord, ...] = ()
    mime_type: str | None = None
    policy_present: bool = False
    policy_attribute_count: int = 0
    spec_version: str | None = None
    raw: object = None


class Mutation(StrEnum):
    """The tamper vocabulary, as properties of the attack rather than the encoding.

    Derived from the 23 ``update_manifest`` / ``update_payload`` call sites in
    ``test_tdfs.py``, ``test_root_signature.py`` and
    ``test_audit_logs_integration.py``, not invented. "Replace the policy with
    one the binding does not cover" is meaningful for any container that binds
    a policy; "edit ``0.manifest.json`` inside the ZIP" is not.
    """

    UNBIND_POLICY = "unbind_policy"
    ALTER_POLICY_BINDING = "alter_policy_binding"
    ALTER_ROOT_SIGNATURE = "alter_root_signature"
    FORGE_GMAC_ROOT = "forge_gmac_root"
    ALTER_SEGMENT_HASH = "alter_segment_hash"
    ALTER_SEGMENT_SIZE = "alter_segment_size"
    ALTER_PAYLOAD_TAIL = "alter_payload_tail"
    ALTER_ASSERTION = "alter_assertion"
    MALICIOUS_KAO = "malicious_kao"
    DUPLICATE_KAO = "duplicate_kao"


@runtime_checkable
class ContainerAdapter(Extension, Protocol):
    """Everything the suite needs to know about a container format.

    ``wire_format`` is what the CLI is handed. ``ztdf-ecwrap`` maps to
    ``ztdf``: it is a variant rather than a distinct format, and carries its
    difference in a flag. That collapse is ``tdfs.simple_container()`` today,
    and it is the in-tree precedent for this whole protocol.

    ``requires_attributes()`` exists because a format whose encrypt path
    demands at least one attribute has no no-attribute roundtrip cell -- and
    the no-attribute roundtrip is xtest's *default*. A format that answers
    ``True`` gets those cells skipped with a reason instead of failing on an
    unhelpful CLI usage error.
    """

    wire_format: str

    def inspect(self, path: Path) -> Inspection: ...

    def tamper(self, path: Path, mutation: Mutation) -> Path:
        """Produce a tampered copy, or raise :class:`UnsupportedMutation`."""
        ...

    def requires_attributes(self) -> bool: ...


@runtime_checkable
class SdkProvider(Extension, Protocol):
    """An SDK name the matrix may fan out over.

    The object on the other end of an ``otdf.adapters`` entry point is the
    typed SDK adapter defined by the adapter ticket. This registry only needs
    the name and the contributed features; it deliberately does not pin the
    rest of that protocol here.
    """

    def versions(self) -> tuple[str, ...]:
        """Installed versions of this SDK, newest-agnostic, in a stable order."""
        ...


@runtime_checkable
class Installer(Protocol):
    """Materialises one version of an SDK under a dist directory."""

    name: str

    def __call__(self, version: str, dest: Path) -> None: ...


# --- the registry -------------------------------------------------------------


@dataclass
class Registry[T]:
    """A name -> object map seeded with built-ins and widened by entry points.

    A built-in may be registered with ``None`` until something supplies the
    object: the *name* set is what the parametrizers and validators need, and
    it is useful before any adapter exists. That is what lets this module land
    as a pure addition.
    """

    group: str
    builtins: tuple[str, ...]
    entry_type: type[T]
    _entries: dict[str, T | None] = field(default_factory=dict, init=False)
    _loaded: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Drop plugin registrations and forget that discovery ran.

        For tests. Entry-point discovery is otherwise once per process.
        """
        self._entries = dict.fromkeys(self.builtins)
        self._loaded = False

    def register(self, name: str, obj: T | None) -> None:
        self._ensure_available(name)
        self._entries[name] = obj

    def _ensure_available(self, name: str) -> None:
        if name in self._entries:
            raise DuplicateName(
                f"{self.group}: {name!r} is already registered. A plugin may "
                "not shadow a built-in or another plugin -- otherwise "
                f"--containers/--sdks would mean different things depending on "
                "what happens to be installed, which is unauditable from a CI log."
            )

    def load(self) -> None:
        """Discover and register everything declared under :attr:`group`.

        Idempotent: each xdist worker configures itself, and a second scan
        would raise :class:`DuplicateName` on every plugin.

        A load failure raises. ``entry_points()`` only reads metadata, so a
        broken plugin is not discovered until ``ep.load()`` executes its
        module; swallowing that would produce a run that quietly tests less
        than it was asked to, with no non-zero exit anywhere, because the
        missing container simply yields fewer cells.
        """
        if self._loaded:
            return
        original_entries = self._entries.copy()
        self._loaded = True
        try:
            for ep in entry_points(group=self.group):
                self._ensure_available(ep.name)
                obj = _load_entry_point(ep)
                if not isinstance(obj, self.entry_type):
                    raise PluginLoadError(
                        f"entry point {ep.name!r} in group {ep.group!r} "
                        f"({ep.value}) loaded an object that does not implement "
                        f"{self.entry_type.__name__}"
                    )
                obj_name = cast(Extension | Installer, obj).name
                if obj_name != ep.name:
                    raise PluginLoadError(
                        f"entry point {ep.name!r} in group {ep.group!r} "
                        f"({ep.value}) loaded an object whose name is {obj_name!r}"
                    )
                self.register(ep.name, obj)
                logger.info("registered %s %r from %s", self.group, ep.name, ep.value)
        except Exception:
            self._entries = original_entries
            self._loaded = False
            raise

    def names(self) -> tuple[str, ...]:
        """Registered names: built-ins in declaration order, then plugins."""
        return tuple(self._entries)

    def get(self, name: str) -> T:
        try:
            obj = self._entries[name]
        except KeyError:
            raise UnknownName(
                f"unknown {self.group} name {name!r}; "
                f"registered: {', '.join(sorted(self._entries))}"
            ) from None
        if obj is None:
            raise UnknownName(
                f"{self.group} name {name!r} is registered but has no "
                "implementation yet"
            )
        return obj

    def objects(self) -> tuple[T, ...]:
        """Every registered implementation, skipping names with none yet."""
        return tuple(o for o in self._entries.values() if o is not None)

    def __contains__(self, name: str) -> bool:
        return name in self._entries

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)


def _load_entry_point(ep: EntryPoint) -> Any:
    try:
        return ep.load()
    except Exception as e:
        raise PluginLoadError(
            f"entry point {ep.name!r} in group {ep.group!r} "
            f"({ep.value}) could not be loaded: {e}"
        ) from e


SDKS: Registry[SdkProvider] = Registry(GROUP_ADAPTERS, BUILTIN_SDKS, SdkProvider)
CONTAINERS: Registry[ContainerAdapter] = Registry(
    GROUP_CONTAINERS, BUILTIN_CONTAINERS, ContainerAdapter
)
INSTALLERS: Registry[Installer] = Registry(GROUP_INSTALLERS, (), Installer)


def load_all() -> None:
    """Run entry-point discovery for every group. Called from ``pytest_configure``.

    ``pytest_configure`` is the only hook late enough for plugins to have been
    imported and early enough to precede ``pytest_generate_tests``, which is
    where the names turn into parameters.
    """
    for r in (SDKS, CONTAINERS, INSTALLERS):
        r.load()


def reset_all() -> None:
    """Undo :func:`load_all`. For tests."""
    for r in (SDKS, CONTAINERS, INSTALLERS):
        r.reset()


def sdk_names() -> tuple[str, ...]:
    return SDKS.names()


def container_names() -> tuple[str, ...]:
    return CONTAINERS.names()


def feature_names() -> frozenset[str]:
    """Built-in feature names plus every one contributed by a loaded plugin."""
    names = set(BUILTIN_FEATURES)
    for registry in (SDKS, CONTAINERS):
        for obj in registry.objects():
            names |= set(getattr(obj, "features", ()))
    return frozenset(names)
