"""Entry-point discovery: name -> adapter factory.

``xtest`` is consumed by four repos that pin it at ``main``. Each of them
drives its own client and has its own reasons to want a cell in the matrix,
and none of them can add one today: the set of SDKs is a closed ``Literal`` in
the test suite's own source, so widening it means editing this repo. An entry
point moves that decision to the installing environment. A consumer declares

.. code-block:: toml

    [project.entry-points."otdf.adapters"]
    myclient = "my_package.adapters:MyAdapter"

and ``load_adapter("myclient", ...)`` finds it with no change here.

The built-ins are registered the same way rather than special-cased, so the
extension path is the path this repo already uses -- the arrangement that
cannot rot, because breaking it breaks the default run.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import cast

from otdf_adapter.protocol import SdkAdapter
from otdf_adapter.subprocess_cli import DEFAULT_SDK_DIR, SubprocessCliAdapter

logger = logging.getLogger("otdf_adapter.registry")

#: The entry-point group adapters register under.
ENTRY_POINT_GROUP = "otdf.adapters"

#: Names this package provides itself. Used only as a fallback for the case
#: where ``otdf_adapter`` is importable but its distribution metadata is not
#: installed -- a source checkout on ``sys.path``, which is how the test suite
#: is run today. Without it, a working import would still fail to resolve its
#: own built-in names, which is a confusing way to learn about packaging.
BUILTIN_ADAPTERS = ("go", "java", "js")


class AdapterNotFoundError(LookupError):
    """No adapter is registered under the requested name."""


AdapterFactory = Callable[..., SdkAdapter]


def available_adapters() -> dict[str, EntryPoint]:
    """Registered adapter names, from every installed distribution."""
    return {ep.name: ep for ep in entry_points(group=ENTRY_POINT_GROUP)}


def adapter_names() -> tuple[str, ...]:
    """Every adapter name that can be loaded, sorted."""
    return tuple(sorted(set(available_adapters()) | set(BUILTIN_ADAPTERS)))


def load_factory(name: str) -> AdapterFactory:
    """Resolve ``name`` to the callable that constructs its adapter."""
    found = available_adapters().get(name)
    if found is not None:
        loaded = found.load()
        if not callable(loaded):
            raise AdapterNotFoundError(
                f"entry point {ENTRY_POINT_GROUP}:{name} resolved to "
                f"{type(loaded).__name__}, which is not callable"
            )
        # `callable` is as far as static checking reaches across an entry
        # point: the object came from a distribution this one does not import.
        # Whether it returns something that satisfies SdkAdapter is checked
        # when it is called, by `load_adapter`.
        return cast(AdapterFactory, loaded)
    if name in BUILTIN_ADAPTERS:
        return SubprocessCliAdapter
    raise AdapterNotFoundError(
        f"no adapter named {name!r}; registered: {', '.join(adapter_names()) or '(none)'}"
    )


def load_adapter(
    name: str,
    version: str = "main",
    sdk_dir: Path | None = None,
    dist_dir: Path | None = None,
) -> SdkAdapter:
    """Construct the adapter registered under ``name`` for one installed build.

    ``dist_dir`` wins when given; otherwise the build is located at
    ``<sdk_dir>/<name>/dist/<version>/``, which is where the installer puts it.
    """
    factory = load_factory(name)
    if dist_dir is not None:
        return factory(name, version, dist_dir=Path(dist_dir))
    root = Path(sdk_dir) if sdk_dir is not None else DEFAULT_SDK_DIR
    return factory(name, version, dist_dir=root / name / "dist" / version)
