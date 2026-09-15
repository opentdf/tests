"""OpenTDF cross-SDK integration test suite.

Importable as a distribution so a downstream repo can depend on the harness
(``tdfs``, ``abac``, ``otdfctl``, the ``fixtures`` package) and add its own
cells, instead of vendoring the tree and running with ``cwd == xtest/``.

The pytest options and parametrization live in :mod:`xtest.plugin`, registered
through the ``pytest11`` entry point rather than a top-level ``conftest.py``.
A bare ``conftest`` installed at the site-packages root collides with a
consumer's own under ``importmode=prepend`` and raises
``ImportPathMismatchError``; an entry-point plugin has a namespaced module name
and is loaded before argument parsing, which is what ``pytest_addoption``
requires. Disable it with ``-p no:xtest``.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
