"""Where the suite looks for things it does not carry.

Two kinds of path exist here. Package data -- the manifest schema, the extra
keys, the golden TDFs -- travels with the distribution and is resolved by
:mod:`xtest.data`. *Environment* paths do not: the built SDK command-line
shims are produced by ``otdf-sdk-mgr`` into a directory chosen by whoever ran
the install, and cannot be inside the wheel.

Until now that directory was the literal string ``"sdk"``, relative to the
process's working directory, so the suite only ran from the source tree. This
module makes it one named override instead.

Each accessor reads the environment on every call rather than capturing it at
import. ``pytest_configure`` therefore stays free to set the variable before
the first :class:`xtest.tdfs.SDK` is constructed, and a unit test can point a
single case at a ``tmp_path`` with ``monkeypatch.setenv`` without reloading the
module.
"""

import os
from pathlib import Path

__all__ = ["DEFAULT_SDK_DIR", "SDK_DIR_ENV", "sdk_dir"]

#: Environment variable naming the directory holding ``<sdk>/dist/<version>/``.
SDK_DIR_ENV = "XT_SDK_DIR"

#: Used when :data:`SDK_DIR_ENV` is unset or empty. Relative, so the historical
#: "run pytest from ``xtest/``" invocation keeps resolving exactly as before.
DEFAULT_SDK_DIR = "sdk"


def sdk_dir() -> Path:
    """Directory containing the per-SDK CLI distributions.

    Layout underneath is ``<sdk>/dist/<version>/cli.sh``, written by
    ``otdf-sdk-mgr`` and by ``setup-cli-tool/action.yaml``.
    """
    return Path(os.environ.get(SDK_DIR_ENV) or DEFAULT_SDK_DIR)
