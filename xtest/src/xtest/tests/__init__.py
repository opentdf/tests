"""xtest's own cells.

A package rather than a rootdir-relative directory so the modules import as
``xtest.tests.test_tdfs`` from wherever they are installed, and so a consumer
can select them with ``pytest --pyargs xtest.tests`` alongside their own suite.
"""
