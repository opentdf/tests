"""Documentation tooling for the benchmark's statistical figures.

Nothing here is imported by the benchmark runtime. ``perf.stats``,
``perf.runner``, and ``perf.report`` do not depend on this package, and no test
collects it -- the figures are prose, not measurement.

Run ``python -m perf.docs.make_figures`` to regenerate the committed SVGs.
"""
