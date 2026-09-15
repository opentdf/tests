"""Typed adapter protocol for driving OpenTDF SDK command-line clients.

``xtest`` reaches an SDK through four layers today, two of which are lossy: a
typed Python call collapses into an ``XT_WITH_*`` environment dict, which
collapses into ``cli.sh <verb> <src> <dst> <fmt>``, which has four positional
slots and nowhere to put an option. This package is the typed seam that
replaces both lossy steps.

The only implementation shipped here is :class:`~otdf_adapter.subprocess_cli.SubprocessCliAdapter`,
which builds exactly the argv and exactly the ``XT_WITH_*`` environment the
current callers build and execs the existing shim. The abstraction lands
first and alone, so the follow-up that writes native per-SDK argv builders has
a stable contract -- and a characterization suite -- to move against.
"""

from otdf_adapter.protocol import (
    DecryptRequest,
    EncryptRequest,
    SdkAdapter,
    SdkVersion,
)
from otdf_adapter.registry import (
    ENTRY_POINT_GROUP,
    AdapterNotFoundError,
    available_adapters,
    load_adapter,
)
from otdf_adapter.subprocess_cli import Command, SubprocessCliAdapter

__version__ = "0.1.0"

__all__ = [
    "ENTRY_POINT_GROUP",
    "AdapterNotFoundError",
    "Command",
    "DecryptRequest",
    "EncryptRequest",
    "SdkAdapter",
    "SdkVersion",
    "SubprocessCliAdapter",
    "available_adapters",
    "load_adapter",
]
