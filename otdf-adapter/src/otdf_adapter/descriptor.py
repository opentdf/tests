"""What an installer leaves behind so a runner knows how to invoke a build.

Today the installer writes a ``.version`` file and the shim re-derives an
argv from it *at run time*: ``module@ver`` means ``go run module@ver``, a bare
tag means the legacy standalone module path, and an absent file means
``@latest``. That is a three-branch decision, duplicated in two shell scripts,
re-evaluated on every single invocation, deriving a fact Python already knew
at install time and threw away.

A descriptor is that fact, written once:

.. code-block:: json

    {"sdk": "go", "version": "v0.31.0", "adapter": "go",
     "exec": ["go", "run", "github.com/opentdf/platform/otdfctl@v0.31.0"]}

Nothing writes one yet -- teaching the installer to is the follow-up, together
with the native adapters that would consume it. What this module does now is
fix the shape, and read today's layout through the same interface via
:meth:`AdapterDescriptor.from_shim`, so the two can coexist while the shims
are still the only implementation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

#: Written into ``dist/<version>/`` beside the artifact it describes.
DESCRIPTOR_NAME = "adapter.json"

#: The shim the descriptor replaces. Still the only thing A1 executes.
SHIM_NAME = "cli.sh"


class DescriptorError(Exception):
    """A descriptor exists but cannot be used."""


@dataclass(frozen=True)
class AdapterDescriptor:
    """How to reach one installed build of one SDK."""

    #: SDK family, e.g. ``go``.
    sdk: str
    #: The installed build, e.g. ``v0.31.0`` or ``main``.
    version: str
    #: Which registered adapter drives it. Usually equal to ``sdk``; distinct
    #: so one adapter implementation can serve several installs.
    adapter: str
    #: argv prefix that runs the client. Never empty.
    exec: tuple[str, ...]
    #: Directory the descriptor was read from.
    dist_dir: Path = Path()

    @classmethod
    def from_shim(cls, sdk: str, version: str, dist_dir: Path) -> AdapterDescriptor:
        """Describe an install that has only a ``cli.sh``.

        The fallback for every build installed before descriptors existed --
        which is all of them.
        """
        return cls(
            sdk=sdk,
            version=version,
            adapter=sdk,
            exec=(str(dist_dir / SHIM_NAME),),
            dist_dir=dist_dir,
        )

    @classmethod
    def load(cls, dist_dir: Path, sdk: str = "", version: str = "") -> AdapterDescriptor:
        """Read ``dist_dir/adapter.json``, falling back to the shim layout.

        A *missing* descriptor is the normal case and is not an error. A
        descriptor that is present but malformed is, because silently falling
        back would run a different build than the one the caller asked for and
        report it under the requested version's name.
        """
        path = dist_dir / DESCRIPTOR_NAME
        if not path.is_file():
            return cls.from_shim(sdk, version, dist_dir)
        try:
            raw = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            raise DescriptorError(f"{path} is not readable JSON: {e}") from e
        if not isinstance(raw, dict):
            raise DescriptorError(f"{path} must contain a JSON object, got {type(raw).__name__}")
        argv = raw.get("exec")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            raise DescriptorError(f"{path} 'exec' must be a non-empty list of strings")
        return cls(
            sdk=str(raw.get("sdk", sdk)),
            version=str(raw.get("version", version)),
            adapter=str(raw.get("adapter") or raw.get("sdk") or sdk),
            exec=tuple(argv),
            dist_dir=dist_dir,
        )

    def to_json(self) -> str:
        """Serialize for an installer to write. ``dist_dir`` is implied by location."""
        return json.dumps(
            {
                "sdk": self.sdk,
                "version": self.version,
                "adapter": self.adapter,
                "exec": list(self.exec),
            }
        )
