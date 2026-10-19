"""Turn benchmark workflow inputs into a validated job matrix.

The workflow used to parse refs, count arms, default budgets and spot
same-commit requests in shell. Every one of those rules also lives in Python,
for local runs, and two copies drift: the shell starts refusing requests the
harness would have accepted, or worse, accepting ones it would not. This
module is the only adapter. It reads the dispatch inputs, applies
:mod:`perf.config` and :mod:`perf.cells`, and writes the matrix and settings
the bench job consumes. It runs in ``resolve-versions``, before any runner
spends fifteen minutes bringing up a platform.

Same-commit requests are *not* detected here: that needs resolution, which
`otdf-sdk-mgr install benchmark` does in the bench job and reports as a
neutral preparation, exactly as it does locally.

Usage (in the workflow)::

    python -m perf.ci >> "$GITHUB_OUTPUT"

Inputs come from ``BENCH_*`` environment variables so that no input value is
ever interpolated into a shell command line.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass

from perf.cells import DEFAULT_PAYLOAD_SPEC, parse_payloads
from perf.config import (
    MAX_ARM_COUNT,
    SDK_NAMES,
    BenchConfig,
    BenchmarkRequest,
    budget_seconds,
    parse_arm_spec,
    parse_refs,
)

#: Installation, platform startup, provisioning and artifact upload, on top
#: of the measurement budget itself.
OVERHEAD_MINUTES = 30

#: GitHub's ceiling for a job on a hosted runner.
MAX_JOB_MINUTES = 360

#: The nightly comparison: the newest release as the reference, then main.
DEFAULT_REFS = ("latest", "main")

#: Refs that name a release rather than a branch. Used only to put the
#: release first when the per-SDK ``*-ref`` inputs are reused as arms, since
#: those were written as "main latest" long before order meant anything.
_RELEASE_RE = re.compile(r"^(latest|lts|([a-z-]+/)?v?\d+\.\d+\.\d+\S*)$")


class InputError(ValueError):
    """A dispatch input the benchmark cannot run."""


@dataclass(frozen=True, slots=True)
class BenchJob:
    """One bench runner: an SDK and its arms, reference first."""

    sdk: str
    refs: tuple[str, ...]

    def to_dict(self) -> dict[str, str]:
        return {"sdk": self.sdk, "refs": " ".join(self.refs)}


@dataclass(frozen=True, slots=True)
class Plan:
    jobs: tuple[BenchJob, ...]
    payloads: str
    budget_seconds: float
    timeout_minutes: int

    def outputs(self) -> dict[str, str]:
        return {
            "matrix": json.dumps([j.to_dict() for j in self.jobs]),
            "payloads": self.payloads,
            "budget-seconds": f"{self.budget_seconds:g}",
            "timeout-minutes": str(self.timeout_minutes),
        }


def _focus(value: str) -> tuple[str, ...]:
    value = value.strip() or "all"
    if value == "all":
        return SDK_NAMES
    if value not in SDK_NAMES:
        raise InputError(
            f"focus-sdk {value!r} is not one of all, {', '.join(SDK_NAMES)}"
        )
    return (value,)


def _arms_from_sdk_ref(sdk: str, value: str) -> tuple[str, ...]:
    """Arms from a per-SDK ``*-ref`` input such as ``"main latest"``.

    Kept so existing dispatches keep meaning what they did: the release is the
    reference and the branch the candidate, whichever order they were typed
    in. Anything more specific belongs in ``bench-refs``, where order is
    explicit.
    """
    tokens = tuple(value.split()) or DEFAULT_REFS
    releases = [t for t in tokens if _RELEASE_RE.match(t)]
    first = releases[0] if releases else tokens[0]
    refs = (first, *(t for t in tokens if t != first))
    if len(refs) < 2:
        raise InputError(
            f"{sdk} needs two builds to compare but its ref input is {value!r}; "
            f"add a release (e.g. '{value} latest') or set bench-refs"
        )
    if len(refs) > MAX_ARM_COUNT:
        raise InputError(
            f"{sdk} ref input names {len(refs)} builds; at most {MAX_ARM_COUNT}"
        )
    BenchmarkRequest(arms=tuple(parse_arm_spec(f"{sdk}@{r}") for r in refs))
    return refs


def plan(env: Mapping[str, str]) -> Plan:
    """Validate the inputs in ``env`` and build the bench plan."""
    focus = _focus(env.get("BENCH_FOCUS_SDK", ""))
    refs_input = env.get("BENCH_REFS", "").strip()
    try:
        if refs_input:
            arms = parse_refs(refs_input)
            sdk = arms[0].name
            if sdk not in focus:
                raise InputError(
                    f"bench-refs names {sdk} but focus-sdk selects {', '.join(focus)}"
                )
            jobs: tuple[BenchJob, ...] = (
                BenchJob(sdk, tuple(a.spec or "" for a in arms)),
            )
            if any(not r for r in jobs[0].refs):
                raise InputError(
                    f"every bench-refs entry needs a version, e.g. {sdk}@main; "
                    f"got {refs_input!r}"
                )
        else:
            jobs = tuple(
                BenchJob(
                    sdk,
                    _arms_from_sdk_ref(sdk, env.get(f"BENCH_{sdk.upper()}_REF", "")),
                )
                for sdk in focus
            )

        payload_spec = env.get("BENCH_PAYLOADS", "").strip() or DEFAULT_PAYLOAD_SPEC
        payloads = ",".join(p.label for p in parse_payloads(payload_spec))

        raw_budget = env.get("BENCH_BUDGET_SECONDS", "").strip()
        explicit = float(raw_budget) if raw_budget else None
        n_arms = max(len(j.refs) for j in jobs)
        budget = budget_seconds(explicit, n_arms)
        # BenchConfig owns the range checks: positive and finite.
        BenchConfig(budget_seconds=budget)
    except ValueError as e:
        raise InputError(str(e)) from e

    timeout = math.ceil(budget / 60) + OVERHEAD_MINUTES
    if timeout > MAX_JOB_MINUTES:
        raise InputError(
            f"a {budget:g}s budget needs a {timeout}-minute job, past GitHub's "
            f"{MAX_JOB_MINUTES}-minute limit; lower bench-budget-seconds to at "
            f"most {(MAX_JOB_MINUTES - OVERHEAD_MINUTES) * 60}"
        )
    return Plan(jobs, payloads, budget, timeout)


def main() -> int:
    try:
        result = plan(os.environ)
    except InputError as e:
        print(f"::error::invalid benchmark inputs: {e}", file=sys.stderr)
        return 1
    for job in result.jobs:
        print(f"{job.sdk}: {' '.join(job.refs)} (reference first)", file=sys.stderr)
    for key, value in result.outputs().items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
