"""Tests for perf/config.py - benchmark option validation.

Every check here exists because its absence produced a run that reported
success without measuring what it claimed to. The interesting assertion in
most of these is not the message but that something is raised at all.
"""

import math
from pathlib import Path
from typing import cast

import pytest

import conftest
from perf import stats
from perf.cells import DEFAULT_PAYLOAD_SPEC
from perf.config import (
    DEFAULT_BOOTSTRAP_RESAMPLES,
    DEFAULT_CONFIDENCE,
    DEFAULT_THRESHOLD,
    MAX_ARM_COUNT,
    MIN_USABLE_ROUNDS,
    PRECISION_FRACTION,
    ArmRequest,
    BenchConfig,
    BenchmarkRequest,
    budget_seconds,
    default_budget_for_arm_count,
    normalize_baseline_candidate,
    parse_arm_spec,
    parse_refs,
    requested_arms,
    validate_sdk_name,
)


class TestArmRequest:
    def test_str_with_spec(self):
        assert str(ArmRequest(name="go", spec="v0.29.0")) == "go@v0.29.0"

    def test_str_without_spec(self):
        assert str(ArmRequest(name="go", spec=None)) == "go"


class TestValidateSdkName:
    @pytest.mark.parametrize("name", ["go", "java", "js"])
    def test_valid_names(self, name: str):
        validate_sdk_name(name)

    def test_invalid_name(self):
        with pytest.raises(ValueError, match="unknown SDK 'python'"):
            validate_sdk_name("python")


class TestParseArmSpec:
    def test_name_and_version(self):
        assert parse_arm_spec("go@v0.29.0") == ArmRequest("go", "v0.29.0")

    def test_bare_name(self):
        assert parse_arm_spec("go") == ArmRequest("go", None)

    def test_version_may_contain_an_at_sign(self):
        assert parse_arm_spec("js@npm@1.2.3") == ArmRequest("js", "npm@1.2.3")

    def test_trailing_at_is_not_a_bare_name(self):
        # "go@" reads as a version the caller meant to type and didn't;
        # treating it as "go" would silently benchmark the default build.
        with pytest.raises(ValueError, match="empty version"):
            parse_arm_spec("go@")


class TestNormalizeBaselineCandidate:
    def test_both_specified(self):
        arms = normalize_baseline_candidate("go@v0.29.0", "go@main")
        assert arms == (ArmRequest("go", "v0.29.0"), ArmRequest("go", "main"))

    def test_both_none_defers_to_arm_selection(self):
        assert normalize_baseline_candidate(None, None) == ()

    @pytest.mark.parametrize(
        ("baseline", "candidate"), [("go@v0.29.0", None), (None, "go@main")]
    )
    def test_one_without_the_other_raises(self, baseline, candidate):
        with pytest.raises(ValueError, match="both .* are required"):
            normalize_baseline_candidate(baseline, candidate)

    def test_different_sdks_raises(self):
        with pytest.raises(ValueError, match="same SDK"):
            normalize_baseline_candidate("go@v0.29.0", "java@main")

    def test_no_version_on_either_side(self):
        arms = normalize_baseline_candidate("go", "go")
        assert arms == (ArmRequest("go", None), ArmRequest("go", None))


class TestBenchConfig:
    def test_defaults_come_from_the_statistics_module(self):
        cfg = BenchConfig()
        assert cfg.threshold == DEFAULT_THRESHOLD
        assert cfg.n_resamples == DEFAULT_BOOTSTRAP_RESAMPLES
        assert cfg.confidence == DEFAULT_CONFIDENCE
        assert cfg.gated_metrics == ("wall", "rss")

    def test_min_rounds_below_the_usable_floor_raises(self):
        with pytest.raises(ValueError, match="min_rounds must be at least"):
            BenchConfig(min_rounds=MIN_USABLE_ROUNDS - 1)

    def test_max_rounds_below_min_raises(self):
        with pytest.raises(ValueError, match="max_rounds must not be below"):
            BenchConfig(min_rounds=30, max_rounds=20)

    def test_negative_warmup_raises(self):
        with pytest.raises(ValueError, match="warmup must not be negative"):
            BenchConfig(warmup=-1)

    @pytest.mark.parametrize("budget", [0.0, -1.0, math.inf, math.nan])
    def test_unusable_budget_raises(self, budget: float):
        # inf is the interesting one: it disables the budget guard while
        # looking like a configured value.
        with pytest.raises(ValueError, match="budget_seconds"):
            BenchConfig(budget_seconds=budget)

    @pytest.mark.parametrize("timeout", [0.0, -1.0, math.inf, math.nan])
    def test_unusable_timeout_raises(self, timeout: float):
        with pytest.raises(ValueError, match="timeout_s"):
            BenchConfig(timeout_s=timeout)

    @pytest.mark.parametrize("threshold", [1.0, 0.95, math.nan])
    def test_threshold_must_exceed_one(self, threshold: float):
        with pytest.raises(ValueError, match="threshold is a ratio above 1.0"):
            BenchConfig(threshold=threshold)

    @pytest.mark.parametrize("confidence", [0.0, 1.0, -0.5, 1.5])
    def test_confidence_outside_the_unit_interval_raises(self, confidence: float):
        with pytest.raises(ValueError, match="confidence must be in"):
            BenchConfig(confidence=confidence)

    def test_non_positive_resamples_raises(self):
        with pytest.raises(ValueError, match="n_resamples must be positive"):
            BenchConfig(n_resamples=0)

    def test_unknown_gated_metric_raises(self):
        with pytest.raises(ValueError, match="unknown gated metrics"):
            BenchConfig(gated_metrics=("wall", "iops"))

    def test_target_half_width_is_a_fraction_of_the_log_threshold(self):
        cfg = BenchConfig(threshold=1.15)
        assert cfg.target_half_width_log == pytest.approx(
            math.log(1.15) * PRECISION_FRACTION
        )


class TestBenchmarkRequest:
    def test_valid_two_arm(self):
        req = BenchmarkRequest(
            arms=(ArmRequest("go", "v0.29.0"), ArmRequest("go", "main"))
        )
        assert req.sdk_name == "go"
        assert req.reference == ArmRequest("go", "v0.29.0")
        assert req.candidates == (ArmRequest("go", "main"),)

    def test_settings_default_to_a_valid_bench_config(self):
        # Composed, not restated: one set of defaults for the round loop and
        # the request that configures it.
        assert (
            BenchmarkRequest(arms=(ArmRequest("go", "main"),)).config == BenchConfig()
        )

    def test_settings_are_carried_through(self):
        cfg = BenchConfig(min_rounds=10, max_rounds=10)
        req = BenchmarkRequest(arms=(ArmRequest("go", "main"),), config=cfg)
        assert req.config.min_rounds == 10

    def test_invalid_settings_raise_through_the_request(self):
        with pytest.raises(ValueError, match="max_rounds must not be below"):
            BenchmarkRequest(
                arms=(ArmRequest("go", "main"),),
                config=BenchConfig(min_rounds=30, max_rounds=20),
            )

    def test_empty_arms_raises(self):
        with pytest.raises(ValueError, match="at least one arm is required"):
            BenchmarkRequest(arms=())

    def test_too_many_arms_raises(self):
        arms = tuple(ArmRequest("go", f"v{i}") for i in range(MAX_ARM_COUNT + 1))
        with pytest.raises(ValueError, match="at most .* arms are supported"):
            BenchmarkRequest(arms=arms)

    def test_mixed_sdks_raises(self):
        with pytest.raises(ValueError, match="same SDK"):
            BenchmarkRequest(
                arms=(ArmRequest("go", "main"), ArmRequest("java", "main"))
            )

    def test_unknown_sdk_raises_rather_than_skipping(self):
        # Arm selection used to answer a typo with a skip, so the run went
        # green having measured nothing.
        with pytest.raises(ValueError, match="unknown SDK"):
            BenchmarkRequest(arms=(ArmRequest("python", "main"),))

    def test_duplicate_arms_raises(self):
        with pytest.raises(ValueError, match="duplicate arm request"):
            BenchmarkRequest(arms=(ArmRequest("go", "main"), ArmRequest("go", "main")))

    def test_no_gate_defaults_off(self):
        assert BenchmarkRequest(arms=(ArmRequest("go", "main"),)).no_gate is False


class TestDefaultBudgetForArmCount:
    def test_two_arms_get_the_base_budget(self):
        assert default_budget_for_arm_count(2) == 1500.0

    def test_four_arms_get_double(self):
        assert default_budget_for_arm_count(4) == 3000.0

    def test_custom_base(self):
        assert default_budget_for_arm_count(2, base_budget=1000.0) == 1000.0
        assert default_budget_for_arm_count(4, base_budget=1000.0) == 2000.0

    def test_arm_count_too_low_raises(self):
        with pytest.raises(ValueError, match="arm_count must be at least 2"):
            default_budget_for_arm_count(1)


class TestParseRefs:
    @pytest.mark.parametrize(
        "spec",
        ["go@v0.29.0,go@main", "go@v0.29.0 go@main go@a", "go@1, go@2 ,go@3,go@4"],
    )
    def test_two_to_four_refs_parse_in_order(self, spec: str):
        arms = parse_refs(spec)
        assert 2 <= len(arms) <= MAX_ARM_COUNT == 4
        assert arms[0].name == "go"
        assert str(arms[0]) == spec.replace(",", " ").split()[0]

    @pytest.mark.parametrize(
        ("spec", "match"),
        [
            ("go@main", "need 2 to 4"),
            ("go@1,go@2,go@3,go@4,go@5", "at most 4"),
            ("go@main,go@main", "duplicate"),
            ("go@main,java@main", "same SDK"),
            ("gp@main,gp@v1", "unknown SDK"),
            ("go@,go@main", "empty version"),
        ],
    )
    def test_invalid_requests_are_refused(self, spec: str, match: str):
        with pytest.raises(ValueError, match=match):
            parse_refs(spec)


class TestRequestedArms:
    def test_baseline_and_candidate_are_an_adapter_onto_refs(self):
        assert requested_arms(None, "go@v0.29.0", "go@main") == parse_refs(
            "go@v0.29.0,go@main"
        )

    def test_mixing_the_forms_is_refused(self):
        with pytest.raises(ValueError, match="cannot be combined"):
            requested_arms("go@a,go@b", "go@v0.29.0", None)

    def test_nothing_named_defers_to_arm_selection(self):
        assert requested_arms(None, None, None) == ()


class TestBudgetSeconds:
    def test_the_default_scales_with_arm_count(self):
        assert budget_seconds(None, 2) == 1500.0
        assert budget_seconds(None, 3) == 2250.0

    def test_an_explicit_budget_is_taken_as_given(self):
        assert budget_seconds(900.0, 4) == 900.0


class _FakeConfig:
    """Just enough of ``pytest.Config`` for the ``--bench`` checks in ``pytest_configure``."""

    def __init__(self, **opts: object):
        self._options: dict[str, object] = {
            "--bench": True,
            "--sdks": "go",
            "--bench-refs": None,
            "--bench-baseline": None,
            "--bench-candidate": None,
            "--bench-threshold": stats.DEFAULT_THRESHOLD,
            "--bench-min-rounds": 20,
            "--bench-max-rounds": 60,
            "--bench-warmup": 5,
            "--bench-budget-seconds": 1500.0,
            "--bench-seed": 0,
            "--bench-payloads": DEFAULT_PAYLOAD_SPEC,
            "numprocesses": None,
        } | opts
        self.stash = pytest.Stash()

    def getoption(self, name: str, default: object = None) -> object:
        return self._options.get(name, default)


def _configure(**opts: object) -> None:
    conftest.pytest_configure(cast(pytest.Config, _FakeConfig(**opts)))


@pytest.fixture(autouse=True)
def _no_ambient_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    # `otdf-local env` exports this; a developer's shell must not change what
    # these tests see.
    monkeypatch.delenv("BENCH_INSTALLATION_MANIFEST", raising=False)


class TestPytestConfigure:
    """The options are checked at configure time, before any session setup."""

    @pytest.mark.parametrize(
        "opts",
        [
            {},
            {"--bench-candidate": "go@main"},
            {"--bench-baseline": "go@v0.29.0"},
            {"--bench-baseline": "go@v0.29.0", "--bench-candidate": "go@main"},
            {"--sdks": "go java", "--bench-candidate": "java@main"},
            {"--sdks": None, "--bench-candidate": "js@main"},
        ],
    )
    def test_accepted(self, opts: dict[str, object]):
        _configure(**opts)

    @pytest.mark.parametrize(
        ("opts", "match"),
        [
            ({"--bench-baseline": "gp@main"}, "unknown SDK 'gp'"),
            ({"--bench-candidate": "go@"}, "empty version"),
            ({"--bench-threshold": 0.9}, "threshold"),
            (
                {"--bench-baseline": "go@main", "--bench-candidate": "java@main"},
                "same SDK",
            ),
            (
                {"--bench-baseline": "go@main", "--bench-candidate": "go@main"},
                "duplicate",
            ),
        ],
    )
    def test_rejected(self, opts: dict[str, object], match: str):
        with pytest.raises(pytest.UsageError, match=match):
            _configure(**opts)

    @pytest.mark.parametrize(
        "opts",
        [
            {"--sdks": "java", "--bench-candidate": "go@main"},
            {"--sdks": "java", "--bench-baseline": "go@v0.29.0"},
            {
                "--sdks": "java",
                "--bench-baseline": "go@v0.29.0",
                "--bench-candidate": "go@main",
            },
        ],
    )
    def test_spec_for_unbenchmarked_sdk_rejected(self, opts: dict[str, object]):
        # The spec would be dropped per-SDK and the run would measure the
        # default builds instead of the one asked for.
        with pytest.raises(pytest.UsageError, match="not being benchmarked"):
            _configure(**opts)

    def test_empty_spec_rejected(self):
        # An empty spec used to mean "use the default"; it is now rejected
        # with everything else that would otherwise be silently ignored.
        with pytest.raises(pytest.UsageError, match="unknown SDK ''"):
            _configure(**{"--bench-baseline": ""})

    def test_multi_arm_refs_accepted(self):
        _configure(**{"--bench-refs": "go@v0.29.0,go@main,go@my-branch"})

    @pytest.mark.parametrize(
        ("opts", "match"),
        [
            (
                {"--bench-refs": "go@a,go@b", "--bench-candidate": "go@main"},
                "cannot be combined",
            ),
            ({"--bench-refs": "go@1,go@2,go@3,go@4,go@5"}, "at most 4"),
            ({"--sdks": "java", "--bench-refs": "go@a,go@b"}, "not being benchmarked"),
        ],
    )
    def test_bad_refs_rejected(self, opts: dict[str, object], match: str):
        with pytest.raises(pytest.UsageError, match=match):
            _configure(**opts)

    def test_an_unreadable_manifest_is_a_usage_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        # Set means "this run was prepared"; measuring whatever is in dist/
        # instead would attach no provenance without saying so.
        monkeypatch.setenv(
            "BENCH_INSTALLATION_MANIFEST", str(tmp_path / "missing.json")
        )
        with pytest.raises(pytest.UsageError, match="cannot read"):
            _configure()

    def test_bad_payload_size_rejected(self):
        # Before the session builds payloads and installs CLIs, as for every
        # other benchmark option.
        with pytest.raises(pytest.UsageError, match="invalid --bench-payloads"):
            _configure(**{"--bench-payloads": "1GB"})

    def test_noop_without_bench(self):
        _configure(**{"--bench": False, "--bench-baseline": "gp@main"})
