"""Performance regression benchmarking for the OpenTDF SDK CLIs.

The suite compares two SDK builds -- typically the latest release against
``main`` -- by running them against each other on the same machine at the same
time. See ``perf/stats.py`` for why the comparison is structured that way.

Modules:
- ``measure``: wall-clock / CPU / peak-RSS for a single CLI invocation.
- ``stats``: the paired statistical comparison and its decision rule.
- ``runner``: the round loop that produces paired samples.
- ``report``: JSON artifacts and GitHub step-summary markdown.
"""
