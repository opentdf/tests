"""Cross-SDK "is this a valid TDF?" suite (DSPX-5349).

Asks every SDK's ``cli.sh validate`` the same question about the same bytes,
and holds each answer to ``baseline.json``:

- the static corpus (:mod:`validity.corpus`) needs no platform -- a few
  hundred hand-built archives, written once per worker and identical for
  every SDK;
- the round trips need a platform: every encrypt SDK's output, for each
  container shape, must be valid to every validator.

A cell fails when the answer differs from the baseline -- in either direction.
A validator growing more lenient fails, and so does a known divergence that
quietly stops reproducing: the fix is then to delete its baseline cell, which
is how the baseline stays honest. SDK builds whose CLI has no ``validate``
command skip through the ``tdf_validity`` feature gate.

"Is this a valid TDF?" is a reader's question, so the validator is the
``decrypt_sdk`` parameter: it follows ``--sdks-decrypt``.
"""

from pathlib import Path

import pytest

import tdfs
from abac import Attribute
from fixtures.encryption import EncryptFactory
from test_tdfs import duplicate_first_kao
from validity import baseline as vb
from validity import corpus
from validity.contract import validate

#: Nothing here reads KAS logs: validation is offline, and the round trips
#: only encrypt.
pytestmark = pytest.mark.no_audit_logs

CASES = corpus.corpus()


@pytest.fixture(scope="session")
def validity_baseline() -> vb.Baseline:
    return vb.load()


@pytest.fixture(scope="session")
def validity_corpus(tmp_dir: Path) -> dict[str, Path]:
    """Every static case on disk, by id. Rewritten only if the bytes changed."""
    return corpus.write(CASES, tmp_dir / "tdf-validity")


def _check(
    case: vb.Spec, validator: tdfs.SDK, tdf_file: Path, baseline: vb.Baseline
) -> None:
    failure = vb.judge(
        case, validator.sdk, str(validator), validate(validator, tdf_file), baseline
    )
    if failure:
        # The message says what differs and what to do about it; a traceback
        # into this helper would only bury it.
        pytest.fail(failure, pytrace=False)


# --- the static corpus -------------------------------------------------------


def _corpus_test(cases: list[corpus.Case]):
    @pytest.mark.parametrize("case", cases, ids=[c.id for c in cases])
    def test_case(
        self,
        case: corpus.Case,
        decrypt_sdk: tdfs.SDK,
        in_focus: set[tdfs.SDK],
        validity_corpus: dict[str, Path],
        validity_baseline: vb.Baseline,
    ):
        del self
        if decrypt_sdk not in in_focus:
            pytest.skip("Not in focus")
        decrypt_sdk.skip_if_unsupported("tdf_validity")
        _check(case, decrypt_sdk, validity_corpus[case.id], validity_baseline)

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

_PLAIN = [s for s in corpus.ROUND_TRIPS if not s.pqc]
_PQC = [s for s in corpus.ROUND_TRIPS if s.pqc]

#: Attribute fixtures (from fixtures/keys.py) that pin each PQ mechanism.
#: Requested lazily, after the platform gate, so a run whose platform reports
#: no PQ mechanism skips instead of registering keys against nothing.
_PQC_ATTRIBUTES = {
    "roundtrip/xwing": "attribute_with_xwing_key",
    "roundtrip/secpmlkem": "attribute_with_secpmlkem_3_key",
    "roundtrip/mlkem-768": "attribute_with_mlkem_768_key",
}


@pytest.mark.parametrize("shape", _PLAIN, ids=[s.id for s in _PLAIN])
def test_roundtrip(
    shape: corpus.RoundTrip,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    assertion_file_no_keys: Path,
    encrypted_tdf: EncryptFactory,
    validity_baseline: vb.Baseline,
):
    """Every encrypt SDK's output is a valid TDF to every validator."""
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    decrypt_sdk.skip_if_unsupported("tdf_validity")
    encrypt_sdk.skip_if_unsupported(*shape.features)

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

    _check(shape, decrypt_sdk, ct_file, validity_baseline)


@pytest.mark.tdf_validity_pqc
@pytest.mark.parametrize("shape", _PQC, ids=[s.id for s in _PQC])
def test_roundtrip_pqc(
    shape: corpus.RoundTrip,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    encrypted_tdf: EncryptFactory,
    validity_baseline: vb.Baseline,
    request: pytest.FixtureRequest,
):
    """As :func:`test_roundtrip`, for the managed PQ keys on km1.

    Separate, and marked, because km1 starts later in the workflow than the
    rest of this module runs: xtest.yml deselects ``-m tdf_validity_pqc`` in
    the standard steps and runs it once the KAS instances are up.
    ML-KEM is expected to be rejected until DSPX-4388 adds ``mlkem-wrapped``
    to the lax schema -- recorded in the baseline, not skipped.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    decrypt_sdk.skip_if_unsupported("tdf_validity")
    tdfs.get_platform_features().skip_if_unsupported(*shape.features)
    encrypt_sdk.skip_if_unsupported(*shape.features)
    if shape.id != "roundtrip/mlkem-768":
        tdfs.skip_pqc_hybrid_format_skew(encrypt_sdk)

    attr, _ = request.getfixturevalue(_PQC_ATTRIBUTES[shape.id])
    ct_file = encrypted_tdf(encrypt_sdk, attr_values=attr.value_fqns)
    _check(shape, decrypt_sdk, ct_file, validity_baseline)


def test_every_round_trip_has_a_recipe():
    """A shape listed in the corpus but never encrypted would never be judged."""
    recipes = {
        "roundtrip/wrapped",
        "roundtrip/ec-wrapped",
        "roundtrip/legacy-4.2.2",
        "roundtrip/assertions",
        "roundtrip/multikao",
    } | set(_PQC_ATTRIBUTES)
    assert {s.id for s in corpus.ROUND_TRIPS} == recipes
