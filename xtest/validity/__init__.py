"""Cross-SDK "is this a valid TDF?" suite (DSPX-5349).

- :mod:`validity.contract`: the ``cli.sh validate`` contract, and running it.
- :mod:`validity.baseline`: ``baseline.json``, and judging answers against it.
- :mod:`validity.corpus`: the static cases, built with :mod:`validity.zipbuild`.
- ``test_tdf_validity.py``: every SDK against the corpus and round trips.
- ``test_tdf_validity_units.py``: the above, offline, on every PR.

See ``spec/tdf-validity.md``.
"""
