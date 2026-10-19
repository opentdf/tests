"""Unit tests for the workflow adapter that validates benchmark inputs.

It is the only place the dispatch inputs are interpreted, so every rule the
workflow used to apply in shell is pinned here instead.
"""

from __future__ import annotations

import json

import pytest

from perf import ci


def plan(**env: str) -> ci.Plan:
    return ci.plan({f"BENCH_{k.upper()}": v for k, v in env.items()})


class TestDefaults:
    def test_the_nightly_measures_latest_against_main_for_every_sdk(self):
        p = plan()
        assert [(j.sdk, j.refs) for j in p.jobs] == [
            ("go", ("latest", "main")),
            ("java", ("latest", "main")),
            ("js", ("latest", "main")),
        ]
        assert p.payloads == "1KiB,1MiB,32MiB"
        assert p.budget_seconds == 1500.0
        assert p.timeout_minutes == 25 + ci.OVERHEAD_MINUTES

    def test_outputs_are_one_line_each(self):
        out = plan(focus_sdk="js").outputs()
        assert json.loads(out["matrix"]) == [{"sdk": "js", "refs": "latest main"}]
        assert all("\n" not in v for v in out.values())


class TestPerSdkRefInputs:
    @pytest.mark.parametrize("value", ["main latest", "latest main"])
    def test_the_release_is_the_reference_whatever_the_order(self, value: str):
        (job,) = plan(focus_sdk="js", js_ref=value).jobs
        assert job.refs == ("latest", "main")

    def test_a_branch_against_a_pinned_release(self):
        (job,) = plan(focus_sdk="java", java_ref="my-branch v0.18.0").jobs
        assert job.refs == ("v0.18.0", "my-branch")

    def test_one_ref_is_refused_before_any_runner_starts(self):
        # It used to install one build, skip every cell, and fail 45 minutes
        # later as NOTHING MEASURED.
        with pytest.raises(ci.InputError, match="two builds"):
            plan(focus_sdk="go", go_ref="main")


class TestBenchRefs:
    def test_names_the_arms_and_narrows_the_matrix(self):
        p = plan(refs="go@v0.29.0,go@main,go@my/branch")
        assert [(j.sdk, j.refs) for j in p.jobs] == [
            ("go", ("v0.29.0", "main", "my/branch"))
        ]
        # Three arms: the default budget scales by 3/2, and the timeout with it.
        assert p.budget_seconds == 2250.0
        assert p.timeout_minutes == 38 + ci.OVERHEAD_MINUTES

    @pytest.mark.parametrize(
        ("env", "match"),
        [
            ({"refs": "go@main"}, "need 2 to 4"),
            ({"refs": "go@1,go@2,go@3,go@4,go@5"}, "at most 4"),
            ({"refs": "go@main,go@main"}, "duplicate"),
            ({"refs": "go@main,js@main"}, "same SDK"),
            ({"refs": "go,go@main"}, "needs a version"),
            ({"refs": "go@a,go@b", "focus_sdk": "js"}, "focus-sdk"),
        ],
    )
    def test_invalid_requests_fail_up_front(self, env: dict[str, str], match: str):
        with pytest.raises(ci.InputError, match=match):
            plan(**env)


class TestSettings:
    def test_payloads_are_canonicalized(self):
        assert plan(payloads="1gib, 1KiB").payloads == "1KiB,1GiB"

    def test_an_explicit_budget_sets_the_timeout(self):
        p = plan(budget_seconds="3600", refs="go@a,go@b,go@c")
        assert p.budget_seconds == 3600.0
        assert p.timeout_minutes == 60 + ci.OVERHEAD_MINUTES

    @pytest.mark.parametrize(
        ("env", "match"),
        [
            ({"payloads": "1GB"}, "payload size"),
            ({"budget_seconds": "0"}, "budget_seconds"),
            ({"budget_seconds": "nan"}, "budget_seconds"),
            ({"budget_seconds": "abc"}, "could not convert"),
            ({"budget_seconds": "99999"}, "360-minute"),
            ({"focus_sdk": "rust"}, "focus-sdk"),
        ],
    )
    def test_bad_settings_fail_up_front(self, env: dict[str, str], match: str):
        with pytest.raises(ci.InputError, match=match):
            plan(**env)
