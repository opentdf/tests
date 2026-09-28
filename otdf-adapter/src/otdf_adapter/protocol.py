"""The typed seam between a test and an SDK's command-line client.

Every option an SDK can be asked for is a named, typed field on a request
object rather than a string in an environment variable. That is the whole
point: ``XT_WITH_*`` exists only because ``cli.sh <verb> <src> <dst> <fmt>``
has four positional slots and nowhere to put an option, so a boolean, a path,
a comma-joined list and a JSON document all had to become strings and then be
re-parsed in bash.

``supports`` takes a **container**. Today's ``cli.sh supports <feature>``
cannot express "this build supports assertions for one container format but
not another", because the shim has no container argument at that point. A
build that gains a second container format therefore has no way to report a
capability that holds for one and not the other, and the caller has no way to
ask. Widening the question here is cheap; widening it in the shell is another
positional slot.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

#: The container format every SDK in this repo can read and write.
DEFAULT_CONTAINER = "ztdf"

#: What the shims pass to ``--mime-type`` unless a caller says otherwise.
DEFAULT_MIME_TYPE = "application/octet-stream"


@dataclass(frozen=True)
class SdkVersion:
    """What an SDK reports about itself.

    Three SDKs answer the same question under three different JSON keys --
    ``.sdk_version``, ``.version`` and ``.["@opentdf/sdk"]`` -- and two of them
    also report a container-schema version separately from their own. Reading
    each of those is one method on one adapter rather than a ``jq`` pipe
    repeated in every ``supports`` case arm.

    ``raw`` is whatever the SDK printed. ``sdk`` and ``schema`` are the parsed
    forms, and both are ``None`` for a branch build that reports something
    unparseable -- which is the common case and must not be an error.
    """

    raw: str
    sdk: str | None = None
    schema: str | None = None
    #: Feature names the SDK volunteers, e.g. go's ``.supported_features``.
    features: tuple[str, ...] = ()


@dataclass(frozen=True)
class EncryptRequest:
    """Everything an encrypt needs, named and typed.

    ``container`` is the wire format; ``ecwrap`` is a wrapping-key choice that
    applies *within* a format. They were fused into a single ``ztdf-ecwrap``
    pseudo-container only because the shim had one slot for both.
    """

    src: Path
    dst: Path
    container: str = DEFAULT_CONTAINER
    mime_type: str | None = DEFAULT_MIME_TYPE
    attributes: Sequence[str] = ()
    assertions: str | None = None
    target_mode: str | None = None
    policy_mode: str = "encrypted"
    ecwrap: bool = False
    ecdsa_binding: bool = False

    def __post_init__(self) -> None:
        # A frozen dataclass is only as immutable as its fields. Callers pass
        # lists (``attr_values=[...]``), and a builder that returned a command
        # holding a caller-owned list would let a later mutation change what a
        # previously-built command runs -- exactly the impurity the
        # determinism test exists to catch.
        object.__setattr__(self, "attributes", tuple(self.attributes))


@dataclass(frozen=True)
class DecryptRequest:
    """Everything a decrypt needs, named and typed."""

    src: Path
    dst: Path
    container: str = DEFAULT_CONTAINER
    assertion_verification_keys: str | None = None
    verify_assertions: bool = True
    ecwrap: bool = False
    kas_allowlist: str | None = None
    ignore_kas_allowlist: bool = False


class AdapterError(Exception):
    """An adapter could not be constructed or driven.

    Distinct from ``subprocess.CalledProcessError``, which means the SDK ran
    and said no. This means the harness is misconfigured -- a missing install,
    an unreadable descriptor -- and no verdict about the SDK is available.
    """


@runtime_checkable
class SdkAdapter(Protocol):
    """Drives one installed build of one SDK.

    An implementation owns its own flag vocabulary. go takes space-separated
    flags (``--host``), java takes ``=``-form (``--platform-endpoint=``) and
    js takes camelCase (``--policyEndpoint``); under the shell contract that
    divergence was a cross-cutting problem solved three times in bash, and
    here it is three small methods.
    """

    #: SDK family: ``go``, ``java``, ``js``, or whatever a consumer registers.
    name: str
    #: The installed build, e.g. ``main`` or ``v0.18.0``.
    version_spec: str

    def encrypt(self, request: EncryptRequest) -> Path:
        """Encrypt ``request.src`` to ``request.dst``; return ``request.dst``."""
        ...

    def decrypt(self, request: DecryptRequest) -> Path:
        """Decrypt ``request.src`` to ``request.dst``; return ``request.dst``."""
        ...

    def supports(self, feature: str, container: str = DEFAULT_CONTAINER) -> bool:
        """Can this build do ``feature`` for ``container``?"""
        ...

    def version(self) -> SdkVersion:
        """What this build reports about itself."""
        ...
