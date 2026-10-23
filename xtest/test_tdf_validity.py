"""Cross-SDK "is this a valid TDF?" suite (DSPX-5349).

Asks every SDK's ``cli.sh validate`` the same question about the same bytes,
and holds each answer to ``tdfvalidity_baseline.json``:

- the static corpus (``tdfvalidity_corpus.py``) needs no platform -- a few
  hundred hand-built archives, written once per worker and identical for
  every SDK;
- the round trips need a platform: every encrypt SDK's output, for each
  container shape, must be valid to every validator.

A cell fails when the answer differs from the baseline -- in either direction.
A validator growing more lenient fails, and so does a known divergence that
quietly stops reproducing: the fix is then to delete its baseline cell, which
is how the baseline stays honest. SDK builds whose CLI has no ``validate``
command skip through the ``tdf_validity`` feature gate.

Every judged cell is also recorded for ``test-results/tdf-validity.json``; see
:mod:`tdfvalidity` and ``spec/tdf-validity.md``.
"""

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

import tdfs
import tdfvalidity
import tdfvalidity_corpus as corpus
from abac import Attribute
from fixtures.encryption import EncryptFactory
from test_tdfs import duplicate_first_kao

#: Nothing here reads KAS logs: validation is offline, and the round trips
#: only encrypt.
pytestmark = pytest.mark.no_audit_logs

CASES = corpus.corpus()

Record = Callable[[tdfvalidity.Verdict], None]


@pytest.fixture(scope="session")
def validity_baseline() -> tdfvalidity.Baseline:
    return tdfvalidity.load_baseline()


@pytest.fixture(scope="session")
def validity_corpus(tmp_dir: Path) -> dict[str, Path]:
    """Every static case on disk, by id. Rewritten only if the bytes changed."""
    return corpus.write(CASES, tmp_dir / "tdf-validity")


@pytest.fixture
def record_verdict(record_property: Callable[[str, object], None]) -> Record:
    def record(verdict: tdfvalidity.Verdict) -> None:
        record_property(tdfvalidity.PROPERTY, tdfvalidity.encode(verdict))

    return record


def _features(shape: corpus.RoundTrip) -> tuple[tdfs.feature_type, ...]:
    """The shape's gate, checked against tdfs's feature names."""
    unknown = set(shape.features) - tdfs.ALL_FEATURES
    assert not unknown, f"{shape.id} names unknown features {sorted(unknown)}"
    return cast(tuple[tdfs.feature_type, ...], shape.features)


def _check(
    case: corpus.Case | corpus.RoundTrip,
    validate_sdk: tdfs.SDK,
    tdf_file: Path,
    baseline: tdfvalidity.Baseline,
    record: Record,
    writer: tdfs.SDK | None = None,
) -> None:
    result = validate_sdk.validate(tdf_file)
    verdict = tdfvalidity.judge(
        case,
        validate_sdk.sdk,
        str(validate_sdk),
        result,
        baseline,
        writer=writer.sdk if writer else None,
    )
    record(verdict)
    if not verdict.ok:
        # The message says what differs and what to do about it; a traceback
        # into this helper would only bury it.
        pytest.fail(verdict.message, pytrace=False)


# --- the static corpus -------------------------------------------------------


def _corpus_test(cases: list[corpus.Case]):
    @pytest.mark.parametrize("case", cases, ids=[c.id for c in cases])
    def test_case(
        self,
        case: corpus.Case,
        validate_sdk: tdfs.SDK,
        in_focus: set[tdfs.SDK],
        validity_corpus: dict[str, Path],
        validity_baseline: tdfvalidity.Baseline,
        record_verdict: Record,
    ):
        del self
        if validate_sdk not in in_focus:
            pytest.skip("Not in focus")
        validate_sdk.skip_if_unsupported("tdf_validity")
        _check(
            case,
            validate_sdk,
            validity_corpus[case.id],
            validity_baseline,
            record_verdict,
        )

    return test_case


# One class per corpus group, so that ``--dist loadscope`` -- which keeps a
# module's free functions on one worker -- can spread the corpus across
# workers. A cold JVM per cell adds up over a few hundred cells.
for _group in dict.fromkeys(c.group for c in CASES):
    _name = "TestCorpus" + "".join(p.title() for p in _group.split("-"))
    globals()[_name] = type(
        _name,
        (),
        {
            "__doc__": f"The static corpus's {_group}/ cases.",
            "test_case": _corpus_test([c for c in CASES if c.group == _group]),
        },
    )


def test_corpus_is_not_empty():
    """A generator that yields nothing would make every class above vanish."""
    assert len(CASES) > 100


# --- round trips -------------------------------------------------------------

_ROUND_TRIPS = {s.id: s for s in corpus.ROUND_TRIPS}
_PLAIN = [s for s in corpus.ROUND_TRIPS if not s.pqc]
_PQC = [s for s in corpus.ROUND_TRIPS if s.pqc]

#: Attribute fixtures (from fixtures/keys.py) that pin each PQ mechanism.
#: Requested lazily, after the platform gate, so a run without the
#: key-management KAS skips instead of registering keys against nothing.
_PQC_ATTRIBUTES = {
    "roundtrip/xwing": "attribute_with_xwing_key",
    "roundtrip/secpmlkem": "attribute_with_secpmlkem_3_key",
    "roundtrip/mlkem-768": "attribute_with_mlkem_768_key",
}


@pytest.mark.parametrize("shape", _PLAIN, ids=[s.id for s in _PLAIN])
def test_roundtrip(
    shape: corpus.RoundTrip,
    encrypt_sdk: tdfs.SDK,
    validate_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    assertion_file_no_keys: Path,
    encrypted_tdf: EncryptFactory,
    validity_baseline: tdfvalidity.Baseline,
    record_verdict: Record,
):
    """Every encrypt SDK's output is a valid TDF to every validator."""
    if not in_focus & {encrypt_sdk, validate_sdk}:
        pytest.skip("Not in focus")
    validate_sdk.skip_if_unsupported("tdf_validity")
    encrypt_sdk.skip_if_unsupported(*_features(shape))

    rsa = attribute_default_rsa.value_fqns
    match shape.id:
        case "roundtrip/wrapped":
            ct_file = encrypted_tdf(encrypt_sdk, attr_values=rsa)
        case "roundtrip/ec-wrapped":
            tdfs.get_platform_features().skip_if_unsupported("ecwrap")
            ct_file = encrypted_tdf(encrypt_sdk, container="ztdf-ecwrap")
        case "roundtrip/legacy-4.2.2":
            ct_file = encrypted_tdf(encrypt_sdk, attr_values=rsa, target_mode="4.2.2")
        case "roundtrip/assertions":
            ct_file = encrypted_tdf(
                encrypt_sdk, attr_values=rsa, az=str(assertion_file_no_keys)
            )
        case "roundtrip/multikao":
            ct_file = tdfs.update_manifest(
                "validity_multikao",
                encrypted_tdf(encrypt_sdk, attr_values=rsa),
                duplicate_first_kao,
            )
        case _:
            raise AssertionError(f"no recipe for {shape.id}")

    _check(shape, validate_sdk, ct_file, validity_baseline, record_verdict, encrypt_sdk)


@pytest.mark.tdf_validity_pqc
@pytest.mark.parametrize("shape", _PQC, ids=[s.id for s in _PQC])
def test_roundtrip_pqc(
    shape: corpus.RoundTrip,
    encrypt_sdk: tdfs.SDK,
    validate_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    encrypted_tdf: EncryptFactory,
    validity_baseline: tdfvalidity.Baseline,
    record_verdict: Record,
    request: pytest.FixtureRequest,
):
    """As :func:`test_roundtrip`, for the managed PQ keys on km1.

    Separate, and marked, because km1 starts later in the workflow than the
    rest of this module runs; see the ``tdf_validity_pqc`` step in xtest.yml.
    ML-KEM is expected to be rejected until DSPX-4388 adds ``mlkem-wrapped``
    to the lax schema -- recorded in the baseline, not skipped.
    """
    if not in_focus & {encrypt_sdk, validate_sdk}:
        pytest.skip("Not in focus")
    validate_sdk.skip_if_unsupported("tdf_validity")
    tdfs.get_platform_features().skip_if_unsupported(*_features(shape))
    encrypt_sdk.skip_if_unsupported(*_features(shape))
    if shape.id != "roundtrip/mlkem-768":
        tdfs.skip_pqc_hybrid_format_skew(encrypt_sdk)

    attr, _ = request.getfixturevalue(_PQC_ATTRIBUTES[shape.id])
    ct_file = encrypted_tdf(encrypt_sdk, attr_values=attr.value_fqns)
    _check(shape, validate_sdk, ct_file, validity_baseline, record_verdict, encrypt_sdk)


def test_every_round_trip_has_a_recipe():
    """A shape listed in the corpus but never encrypted would never be judged."""
    recipes = {
        "roundtrip/wrapped",
        "roundtrip/ec-wrapped",
        "roundtrip/legacy-4.2.2",
        "roundtrip/assertions",
        "roundtrip/multikao",
    } | set(_PQC_ATTRIBUTES)
    assert set(_ROUND_TRIPS) == recipes
