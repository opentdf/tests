"""Files the suite reads rather than generates, resolved through the package.

``manifest.schema.json``, ``extra-keys.json`` and ``golden/*.tdf`` used to be
opened by a path relative to the process's working directory, which only
resolved when that directory happened to be the source tree. They are package
data now, so the lookup follows the installed package instead.

``test.env`` is deliberately absent: it carries a deployment's endpoint and
client credentials, is generated per environment, and must never be baked into
a wheel.
"""

from importlib.resources import files
from pathlib import Path

__all__ = ["data_path", "extra_keys_file", "golden_file", "manifest_schema_file"]


def data_path(*parts: str) -> Path:
    """Absolute path to a packaged data file.

    Returns a real :class:`~pathlib.Path` because most of these files are
    handed to a subprocess, which cannot be given a ``Traversable``. Every
    supported install (wheel, editable, source tree) unpacks to the filesystem;
    a zipimported package would not, so say so loudly rather than fail later
    inside an SDK shim with an unrecognisable error.
    """
    ref = files(__name__).joinpath(*parts)
    if not isinstance(ref, Path):
        raise RuntimeError(
            f"xtest data is not on the filesystem ({ref!r}); "
            "install the wheel rather than running from a zipimport"
        )
    return ref


def golden_file(name: str) -> Path:
    """A pinned legacy TDF from ``data/golden/``."""
    return data_path("golden", name)


def manifest_schema_file() -> Path:
    """The TDF manifest JSON Schema used by ``tdfs.validate_manifest_schema``."""
    return data_path("manifest.schema.json")


def extra_keys_file() -> Path:
    """Key material the ABAC fixtures register beyond the platform's own."""
    return data_path("extra-keys.json")
