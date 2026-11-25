"""Live corpus checks against km1/km2: key setup and per-SDK decrypt verdicts."""

import os
from pathlib import Path
from typing import cast

import pytest

import abac
import assertions
import corpus
import tdfs
from audit_logs import AuditLogAsserter
from corpus import Sidecar
from corpus_kas import public_matches, supported_keys
from fixtures.assertions import write_assertion_verification_keys_to_file
from otdfctl import OpentdfCommandLineTool

pytestmark = pytest.mark.corpus

DECRYPT_TIMEOUT = 120
STDERR_TAIL = 2048
REPO_ROOT = Path(__file__).parent.parent


def _sidecars() -> dict[str, Sidecar]:
    # Goldens carry no [sdk] table; test_legacy.py covers them.
    return {
        f.name: corpus.load_sidecar(f.with_name(f.name + corpus.SIDECAR_SUFFIX))
        for f in corpus.fixtures()
        if not f.name.startswith("golden-")
    }


def pytest_generate_tests(metafunc: pytest.Metafunc):
    if "corpus_fixture" not in metafunc.fixturenames:
        return
    metafunc.parametrize("corpus_fixture", list(_sidecars()))


def test_corpus_keys_imported(
    otdfctl: OpentdfCommandLineTool,
    corpus_kas: dict[str, abac.KasKey],
    kas_entry_km1: abac.KasEntry,
    kas_entry_km2: abac.KasEntry,
):
    kases = {"km1": kas_entry_km1, "km2": kas_entry_km2}
    expected = supported_keys(tdfs.get_platform_features().features)
    for kid, entry in expected.items():
        listed = otdfctl.kas_registry_keys_list(kases[entry["kas"]])
        key = next((k for k in listed if k.key.key_id == kid), None)
        assert key is not None, f"{kid} missing from {entry['kas']}"
        assert public_matches(entry, key.key.public_key_ctx.pem), kid
        assert kid in corpus_kas


def _tail(data: bytes) -> str:
    return data[-STDERR_TAIL:].decode("utf-8", "replace")


def test_corpus_fixture(
    corpus_fixture: str,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    corpus_kas: dict[str, abac.KasKey],
    request: pytest.FixtureRequest,
    tmp_dir: Path,
    audit_logs: AuditLogAsserter,
):
    if decrypt_sdk not in in_focus:
        pytest.skip(f"{decrypt_sdk} not in focus")
    sc = _sidecars()[corpus_fixture]
    manifest = corpus.read_manifest(sc.fixture)
    features = cast(
        list[tdfs.feature_type], corpus.required_features(manifest, corpus.kas_keys())
    )
    if features:
        tdfs.skip_if_unsupported(decrypt_sdk, *features)
    if corpus.has_data_attributes(manifest):
        tdfs.get_platform_features().skip_if_unsupported("autoconfigure")

    work = tmp_dir / "corpus" / f"{corpus_fixture}-{decrypt_sdk}"
    work.mkdir(parents=True, exist_ok=True)
    keys = corpus.assertion_verification_keys(sc.raw, manifest)
    keys_file = ""
    if keys is not None:
        keys_file = str(
            write_assertion_verification_keys_to_file(
                work,
                "corpus",
                assertions.AssertionVerificationKeys.model_validate(keys),
            )
        )
    out = work / "out.bin"
    out.unlink(missing_ok=True)
    cmd, local_env = decrypt_sdk.decrypt_command(
        sc.fixture, out, "ztdf", assert_keys=keys_file, verify_assertions=True
    )
    mark = audit_logs.mark("before_decrypt")
    try:
        proc = corpus.run_decrypt(
            cmd, cast(dict[str, str], os.environ | local_env), DECRYPT_TIMEOUT
        )
    except corpus.DecryptHung:
        pytest.fail(f"decrypt hung: {corpus_fixture} with {decrypt_sdk}")
    expected = sc.sdk.plaintext_sha256 if sc.sdk else None
    outcome = corpus.classify_outcome(proc.returncode, out, expected)
    stderr = _tail(proc.stderr)
    sdk_semver = decrypt_sdk.semver()
    plat = corpus.platform_semver()

    record = request.config.getoption("--corpus-record")
    if record is not None:
        corpus.append_record(
            record,
            corpus.make_record(
                fixture=corpus_fixture,
                sdk=decrypt_sdk.sdk,
                version=decrypt_sdk.version,
                outcome=outcome,
                out=out,
                sdk_semver=sdk_semver,
                stderr_tail=stderr,
            ),
        )
        return

    assert sc.sdk is not None, f"{corpus_fixture}: sidecar has no [sdk] table"
    assert outcome != "wrong-plaintext", (
        f"{corpus_fixture} with {decrypt_sdk}: wrong plaintext\n{stderr}"
    )
    verdict = corpus.resolve_verdict(sc.sdk, decrypt_sdk.sdk, sdk_semver, plat)
    sidecar = sc.fixture.with_name(sc.fixture.name + corpus.SIDECAR_SUFFIX)
    assert outcome == verdict, (
        f"{corpus_fixture} with {decrypt_sdk}: recorded {verdict}, observed {outcome}\n"
        f"expected verdicts: [sdk] in {os.path.relpath(sidecar, REPO_ROOT)}; see"
        ' "When a corpus cell goes red" in xtest/corpus/README.md\n'
        f"stderr tail:\n{stderr}"
    )
    # Only a decrypt is sure to reach KAS; many rejections fail before rewrap.
    if outcome == "decrypt":
        uuid = corpus.policy_uuid(manifest)
        assert uuid, f"{corpus_fixture}: decrypted, but its policy has no uuid"
        audit_logs.assert_rewrap_success(policy_uuid=uuid, since_mark=mark)
