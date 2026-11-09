"""Assertion verification across SDK pairings (DSPX-1561 Phase 0).

One feature gate, force-only until a release ships:

``assertion_header_key_pinning``
    Each assertion is verified with exactly one key the reader selects from
    its own configuration -- the per-ID key, else the default key, else the
    payload key with HS256 -- and with that key's algorithm. A ``jwk`` or
    ``x5c`` in the binding JWS may only match the selected key.

The assertions under test are built here and written into a TDF that the
encrypting SDK produced. A binding covers only the assertion and the
aggregate of the segment hashes, both manifest data, so building one needs no
payload key. Before any SDK sees a built assertion, the reference reader in
``assertions.py`` confirms that it is signed by the key that built it and
predicts the reason a conforming reader reports, so a red cell is about the
reader rather than a broken fixture.

Every rejection is checked by its spec Section 9 reason (``reason=<code>`` in
the CLI output), not by the exit code, and every rejection has a positive
control: the same verification configuration accepting the authorized or
unaltered artifact.
"""

import filecmp
import hashlib
import hmac
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import assertions
import tdfs
from abac import Attribute
from fixtures.encryption import EncryptFactory
from jsontext import text
from test_tdfs import assert_tamper_error

#### KEYS AND ASSERTIONS

SCHEMA = "urn:nato:stanag:5636:A:1:elements:json"
POLICY_ID = "62c76c68-d73d-4628-8ccc-4c1e18118c22"

#: Ids of the assertions in fixtures/assertions.py.
UNKEYED_ID = "424ff3a3-50ca-4f01-a2ae-ef851cd3cac0"
HS256_ID = "assertion1"
RS256_ID = "assertion2"
#: The id this module gives an assertion it appends.
APPENDED_ID = "assertion3"


@dataclass(frozen=True)
class RsaSigner:
    """An RS256 signing key with its public forms."""

    private: rsa.RSAPrivateKey
    certificate: str

    @classmethod
    def of(cls, private: rsa.RSAPrivateKey, name: str) -> RsaSigner:
        serial = int.from_bytes(name.encode()[:8], "big")
        return cls(private, assertions.self_signed_certificate(private, name, serial))

    @property
    def public_pem(self) -> str:
        return (
            self.private.public_key()
            .public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("ascii")
        )

    @property
    def key(self) -> assertions.VerificationKey:
        return assertions.VerificationKey("RS256", self.private.public_key())

    def header(self, *embedded: str) -> dict[str, Any]:
        """JOSE header members embedding this key as ``jwk`` and/or ``x5c``."""
        members: dict[str, Any] = {}
        if "jwk" in embedded:
            members["jwk"] = assertions.rsa_public_jwk(
                self.private.public_key(), use="sig", alg="RS256"
            )
        if "x5c" in embedded:
            members["x5c"] = [self.certificate]
        return members


@pytest.fixture(scope="module")
def authorized(rs256_keys: tuple[str, str]) -> RsaSigner:
    """The RS256 key the reader configures, which also signs writer assertions."""
    private = serialization.load_pem_private_key(rs256_keys[0].encode(), password=None)
    assert isinstance(private, rsa.RSAPrivateKey)
    return RsaSigner.of(private, "xtest authorized signer")


@pytest.fixture(scope="module")
def unrelated() -> RsaSigner:
    """An RSA key no reader configures."""
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return RsaSigner.of(private, "xtest unrelated key")


#: An HMAC secret no reader configures.
UNRELATED_SECRET = b"xtest: an HMAC secret no reader configures"
#: Stands in for the payload key, which this module never sees, when the
#: reference reader predicts a reason that the key bytes cannot change.
UNKNOWN_PAYLOAD_KEY = assertions.VerificationKey("HS256", b"unknown payload key")


def label(id: str, cls: str = "SECRET") -> dict[str, Any]:
    """A STANAG 5636 classification assertion with a string value."""
    value = {"ocl": {"pol": POLICY_ID, "cls": cls, "dcr": "2024-10-21T20:47:36Z"}}
    return {
        "id": id,
        "type": "handling",
        "scope": "tdo",
        "appliesToState": "encrypted",
        "statement": {
            "format": "json+stanag5636",
            "schema": SCHEMA,
            "value": json.dumps(value, separators=(",", ":")),
        },
    }


def unbound(a: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in a.items() if k != "binding"}


#### MANIFESTS


def _legacy(m: dict[str, Any]) -> bool:
    # The Go and Java rule: no schemaVersion means 4.2.2 encodings.
    return not m.get("schemaVersion")


def bind(
    m: dict[str, Any], a: dict[str, Any], signer: assertions.Signer, **kwargs: Any
):
    """``a`` signed for manifest ``m``'s payload."""
    return assertions.sign_assertion(
        a,
        signer,
        aggregate=assertions.manifest_aggregate(m),
        legacy=_legacy(m),
        **kwargs,
    )


def writer_assertion(m: dict[str, Any], id: str) -> dict[str, Any]:
    found = [a for a in m.get("assertions") or [] if a.get("id") == id]
    assert len(found) == 1, f"writer emitted {len(found)} assertions with id {id!r}"
    return found[0]


def check_signed_by(
    m: dict[str, Any],
    a: dict[str, Any],
    key: assertions.VerificationKey,
    hash_hex: str | None = None,
) -> None:
    """``a``'s binding is ``key``'s valid signature over claims for this payload.

    The claims must carry ``hash_hex``, by default the assertion's true hash.
    Embedded keys are ignored: this says who signed, not whom to trust.
    """
    jws = assertions.parse_jws(a["binding"]["signature"])
    if isinstance(key.material, bytes):
        mac = hmac.new(key.material, jws.signing_input, hashlib.sha256).digest()
        assert hmac.compare_digest(mac, jws.signature), "fixture MAC is wrong"
    else:
        key.material.verify(
            jws.signature, jws.signing_input, padding.PKCS1v15(), hashes.SHA256()
        )
    h = assertions.assertion_hash(a) if hash_hex is None else hash_hex
    expected = assertions.binding_claims(
        h, assertions.manifest_aggregate(m), _legacy(m)
    )
    assert jws.claims == expected, "fixture claims do not bind this payload"


def predict(
    m: dict[str, Any], a: dict[str, Any], key: assertions.VerificationKey
) -> str | None:
    """The reason a conforming reader reports for ``a`` with ``key``, or None."""
    try:
        parsed = assertions.parse_assertion(text(a))
        assertions.assertion_id(parsed)
        assertions.verify_assertion_binding(
            parsed, key, assertions.manifest_aggregate(m), _legacy(m)
        )
    except assertions.AssertionFailure as e:
        return e.reason
    return None


def with_assertions(
    ct_file: Path, scenario: str, build: Callable[[dict[str, Any]], list[Any]]
) -> Path:
    """A copy of ``ct_file`` whose ``assertions`` are ``build(manifest)``."""

    def change(raw: str) -> str:
        m = json.loads(raw)
        m["assertions"] = build(m)
        return text(m)

    return tdfs.update_manifest_text(scenario, ct_file, change)


def verification_file(
    tmp_dir: Path,
    name: str,
    keys: dict[str, tuple[str, str]] | None = None,
    default: tuple[str, str] | None = None,
) -> Path:
    """A CLI verification-keys file: per-ID ``keys`` and an optional default."""
    doc: dict[str, Any] = {
        "keys": {
            id: {"alg": alg, "key": key} for id, (alg, key) in (keys or {}).items()
        }
    }
    if default:
        doc["defaultKey"] = {"alg": default[0], "key": default[1]}
    path = tmp_dir / f"assertion-verification-{name}.json"
    path.write_text(json.dumps(doc))
    return path


#### READERS


def skip_unless(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    feature: tdfs.feature_type,
) -> None:
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    decrypt_sdk.skip_if_unsupported("assertion_verification", feature)


def decrypts(
    decrypt_sdk: tdfs.SDK,
    ct_file: Path,
    rt_file: Path,
    pt_file: Path,
    keys: Path | None = None,
) -> None:
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf", str(keys) if keys else "")
    assert filecmp.cmp(pt_file, rt_file)


def fails_with(
    decrypt_sdk: tdfs.SDK,
    ct_file: Path,
    rt_file: Path,
    reason: str,
    keys: Path | None = None,
) -> bytes:
    """Decrypt must fail, reporting ``reason`` (DSPX-1561 decisions, Section 3).

    Returns the CLI's output, for checks on the rest of the message.
    """
    try:
        decrypt_sdk.decrypt(
            ct_file, rt_file, "ztdf", str(keys) if keys else "", expect_error=True
        )
    except subprocess.CalledProcessError as exc:
        assert f"reason={reason}".encode() in exc.output, (
            f"{decrypt_sdk} rejected {ct_file.name} without reason={reason}: "
            f"{exc.output[-4000:]!r}"
        )
        assert_tamper_error(exc, "assertion", decrypt_sdk)
        return exc.output
    pytest.fail(f"{decrypt_sdk} decrypted {ct_file.name}; expected reason={reason}")


@pytest.fixture
def keyed_ct(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    assertion_file_rs_and_hs_keys: str,
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
) -> Callable[[], Path]:
    """A TDF with writer-signed assertions: HS256 (``assertion1``), RS256
    (``assertion2``), and whatever the writer adds itself."""
    return lambda: encrypted_tdf(
        encrypt_sdk,
        az=assertion_file_rs_and_hs_keys,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )


@pytest.fixture
def unkeyed_ct(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    assertion_file_no_keys: str,
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
) -> Callable[[], Path]:
    """A TDF whose assertions the writer signed with the payload key."""
    return lambda: encrypted_tdf(
        encrypt_sdk,
        az=assertion_file_no_keys,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )


@pytest.fixture
def plain_ct(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
) -> Callable[[], Path]:
    """A TDF written with no assertions requested; some writers add their own."""
    return lambda: encrypted_tdf(
        encrypt_sdk,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )


#### assertion_header_key_pinning

Config = Literal["per-id", "default"]
Placement = Literal["appended", "replacing"]


def pinned_keys(
    tmp_dir: Path, config: Config, signer: RsaSigner, placement: Placement
) -> Path:
    pin = ("RS256", signer.public_pem)
    if config == "default":
        return verification_file(tmp_dir, f"default-{placement}", default=pin)
    return verification_file(
        tmp_dir, f"per-id-{placement}", keys={RS256_ID: pin, APPENDED_ID: pin}
    )


def placed(
    m: dict[str, Any], placement: Placement, signer: RsaSigner, *embedded: str
) -> tuple[list[Any], dict[str, Any]]:
    """The assertions of a TDF where ``signer`` placed a new label.

    Replacing: the writer's RS256 assertion becomes a different label under
    the same id. Appended: a label with a new id follows it. Either way the
    writer's other assertions are dropped, so that only RS256 assertions
    remain for the configuration to verify.
    """
    if placement == "replacing":
        new = bind(
            m,
            label(RS256_ID, "UNCLASSIFIED"),
            signer.private,
            header=signer.header(*embedded),
        )
        return [new], new
    new = bind(m, label(APPENDED_ID), signer.private, header=signer.header(*embedded))
    return [writer_assertion(m, RS256_ID), new], new


@pytest.mark.parametrize("config", ["per-id", "default"])
@pytest.mark.parametrize("placement", ["appended", "replacing"])
@pytest.mark.parametrize("embedded", ["jwk", "x5c"])
def test_embedded_key_cannot_replace_configured_key(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    keyed_ct: Callable[[], Path],
    encrypted_tdf: EncryptFactory,
    tmp_dir: Path,
    authorized: RsaSigner,
    unrelated: RsaSigner,
    config: Config,
    placement: Placement,
    embedded: str,
):
    """A label signed by an unconfigured key that embeds itself is refused."""
    skip_unless(encrypt_sdk, decrypt_sdk, in_focus, "assertion_header_key_pinning")

    def build(m: dict[str, Any]) -> list[Any]:
        listed, new = placed(m, placement, unrelated, embedded)
        check_signed_by(m, new, unrelated.key)
        assert predict(m, new, authorized.key) == "signer-not-permitted"
        return listed

    ct = with_assertions(keyed_ct(), f"embedded-{embedded}-{placement}", build)
    fails_with(
        decrypt_sdk,
        ct,
        encrypted_tdf.rt_file(ct, decrypt_sdk, config),
        "signer-not-permitted",
        pinned_keys(tmp_dir, config, authorized, placement),
    )


@pytest.mark.parametrize("config", ["per-id", "default"])
@pytest.mark.parametrize("placement", ["appended", "replacing"])
def test_configured_key_accepts_its_signer(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    keyed_ct: Callable[[], Path],
    encrypted_tdf: EncryptFactory,
    pt_file: Path,
    tmp_dir: Path,
    authorized: RsaSigner,
    config: Config,
    placement: Placement,
):
    """Positive control: the configured signer, embedding its own jwk and x5c."""
    skip_unless(encrypt_sdk, decrypt_sdk, in_focus, "assertion_header_key_pinning")

    def build(m: dict[str, Any]) -> list[Any]:
        listed, new = placed(m, placement, authorized, "jwk", "x5c")
        assert predict(m, new, authorized.key) is None
        return listed

    ct = with_assertions(keyed_ct(), f"authorized-{placement}", build)
    decrypts(
        decrypt_sdk,
        ct,
        encrypted_tdf.rt_file(ct, decrypt_sdk, config),
        pt_file,
        pinned_keys(tmp_dir, config, authorized, placement),
    )


def _with_payload_key_replacement(
    m: dict[str, Any], placement: Placement, resigned: dict[str, Any]
) -> list[Any]:
    if placement == "replacing":
        return [a for a in m["assertions"] if a.get("id") != UNKEYED_ID] + [resigned]
    return [*m["assertions"], resigned]


@pytest.mark.parametrize("placement", ["appended", "replacing"])
@pytest.mark.parametrize("embedded", ["jwk", "x5c"])
def test_embedded_key_cannot_replace_payload_key(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    unkeyed_ct: Callable[[], Path],
    encrypted_tdf: EncryptFactory,
    unrelated: RsaSigner,
    placement: Placement,
    embedded: str,
):
    """With no keys configured, an RS256 label with its own key is refused."""
    skip_unless(encrypt_sdk, decrypt_sdk, in_focus, "assertion_header_key_pinning")
    id = UNKEYED_ID if placement == "replacing" else APPENDED_ID

    def build(m: dict[str, Any]) -> list[Any]:
        resigned = bind(
            m,
            label(id, "UNCLASSIFIED"),
            unrelated.private,
            header=unrelated.header(embedded),
        )
        check_signed_by(m, resigned, unrelated.key)
        assert predict(m, resigned, UNKNOWN_PAYLOAD_KEY) == "algorithm-mismatch"
        return _with_payload_key_replacement(m, placement, resigned)

    ct = with_assertions(unkeyed_ct(), f"payload-rs256-{embedded}-{placement}", build)
    fails_with(
        decrypt_sdk, ct, encrypted_tdf.rt_file(ct, decrypt_sdk), "algorithm-mismatch"
    )


@pytest.mark.parametrize("placement", ["appended", "replacing"])
def test_hmac_embedded_key_with_payload_key(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    unkeyed_ct: Callable[[], Path],
    encrypted_tdf: EncryptFactory,
    placement: Placement,
):
    """With no keys configured, an HS256 label carrying a jwk is refused."""
    skip_unless(encrypt_sdk, decrypt_sdk, in_focus, "assertion_header_key_pinning")
    id = UNKEYED_ID if placement == "replacing" else APPENDED_ID
    oct_jwk = {"kty": "oct", "k": assertions.b64url(UNRELATED_SECRET)}

    def build(m: dict[str, Any]) -> list[Any]:
        resigned = bind(
            m,
            label(id, "UNCLASSIFIED"),
            UNRELATED_SECRET,
            alg="HS256",
            header={"jwk": oct_jwk},
        )
        check_signed_by(
            m, resigned, assertions.VerificationKey("HS256", UNRELATED_SECRET)
        )
        assert predict(m, resigned, UNKNOWN_PAYLOAD_KEY) == "invalid-embedded-key"
        return _with_payload_key_replacement(m, placement, resigned)

    ct = with_assertions(unkeyed_ct(), f"payload-hs256-jwk-{placement}", build)
    fails_with(
        decrypt_sdk, ct, encrypted_tdf.rt_file(ct, decrypt_sdk), "invalid-embedded-key"
    )


def test_payload_key_accepts_writer_assertions(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    unkeyed_ct: Callable[[], Path],
    encrypted_tdf: EncryptFactory,
    pt_file: Path,
):
    """Positive control for the payload-key cases: the writer's own bindings."""
    skip_unless(encrypt_sdk, decrypt_sdk, in_focus, "assertion_header_key_pinning")
    ct = unkeyed_ct()
    decrypts(decrypt_sdk, ct, encrypted_tdf.rt_file(ct, decrypt_sdk), pt_file)


def test_per_id_key_failure_does_not_try_default_key(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    keyed_ct: Callable[[], Path],
    encrypted_tdf: EncryptFactory,
    pt_file: Path,
    tmp_dir: Path,
    authorized: RsaSigner,
    unrelated: RsaSigner,
):
    """keys[id] is the wrong key and the default is the right one: refused.

    The control signs the same label with the key keys[id] names, which the
    same configuration accepts.
    """
    skip_unless(encrypt_sdk, decrypt_sdk, in_focus, "assertion_header_key_pinning")
    keys = verification_file(
        tmp_dir,
        "per-id-wrong-default-right",
        keys={RS256_ID: ("RS256", unrelated.public_pem)},
        default=("RS256", authorized.public_pem),
    )

    def writer_signed(m: dict[str, Any]) -> list[Any]:
        a = writer_assertion(m, RS256_ID)
        assert predict(m, a, unrelated.key) == "signature-invalid"
        return [a]

    def resigned(m: dict[str, Any]) -> list[Any]:
        a = bind(m, unbound(writer_assertion(m, RS256_ID)), unrelated.private)
        assert predict(m, a, unrelated.key) is None
        return [a]

    control = with_assertions(keyed_ct(), "rs256-resigned-unrelated", resigned)
    decrypts(
        decrypt_sdk, control, encrypted_tdf.rt_file(control, decrypt_sdk), pt_file, keys
    )
    ct = with_assertions(keyed_ct(), "rs256-only", writer_signed)
    fails_with(
        decrypt_sdk,
        ct,
        encrypted_tdf.rt_file(ct, decrypt_sdk),
        "signature-invalid",
        keys,
    )


def test_default_key_failure_does_not_try_payload_key(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    unkeyed_ct: Callable[[], Path],
    encrypted_tdf: EncryptFactory,
    pt_file: Path,
    tmp_dir: Path,
    authorized: RsaSigner,
):
    """A default RS256 key refuses the writer's payload-key bindings.

    The control replaces them with the same label signed by the default key.
    """
    skip_unless(encrypt_sdk, decrypt_sdk, in_focus, "assertion_header_key_pinning")
    keys = verification_file(
        tmp_dir, "default-rs256", default=("RS256", authorized.public_pem)
    )

    def writer_signed(m: dict[str, Any]) -> list[Any]:
        a = writer_assertion(m, UNKEYED_ID)
        assert predict(m, a, authorized.key) == "algorithm-mismatch"
        return [a]

    def resigned(m: dict[str, Any]) -> list[Any]:
        a = bind(m, unbound(writer_assertion(m, UNKEYED_ID)), authorized.private)
        assert predict(m, a, authorized.key) is None
        return [a]

    control = with_assertions(unkeyed_ct(), "unkeyed-resigned-authorized", resigned)
    decrypts(
        decrypt_sdk, control, encrypted_tdf.rt_file(control, decrypt_sdk), pt_file, keys
    )
    ct = with_assertions(unkeyed_ct(), "unkeyed-only", writer_signed)
    fails_with(
        decrypt_sdk,
        ct,
        encrypted_tdf.rt_file(ct, decrypt_sdk),
        "algorithm-mismatch",
        keys,
    )


@pytest.mark.parametrize("alg", ["RS256", "HS256"])
def test_default_key_only_verification_file(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    keyed_ct: Callable[[], Path],
    encrypted_tdf: EncryptFactory,
    pt_file: Path,
    tmp_dir: Path,
    authorized: RsaSigner,
    hs256_key: str,
    alg: str,
):
    """A verification-keys file with only defaultKey verifies writer bindings."""
    skip_unless(encrypt_sdk, decrypt_sdk, in_focus, "assertion_header_key_pinning")
    if alg == "RS256":
        id, key, pin = RS256_ID, authorized.key, authorized.public_pem
    else:
        # The CLIs take an HS256 key string's UTF-8 bytes as the secret.
        id, key, pin = (
            HS256_ID,
            assertions.VerificationKey("HS256", hs256_key.encode()),
            hs256_key,
        )

    def only(m: dict[str, Any]) -> list[Any]:
        a = writer_assertion(m, id)
        assert predict(m, a, key) is None
        return [a]

    ct = with_assertions(keyed_ct(), f"{alg.lower()}-only", only)
    decrypts(
        decrypt_sdk,
        ct,
        encrypted_tdf.rt_file(ct, decrypt_sdk),
        pt_file,
        verification_file(tmp_dir, f"default-only-{alg}", default=(alg, pin)),
    )


def test_default_key_applies_to_payload_key_assertions(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    plain_ct: Callable[[], Path],
    encrypted_tdf: EncryptFactory,
    pt_file: Path,
    tmp_dir: Path,
    authorized: RsaSigner,
):
    """A default key also covers the payload-key system-metadata assertion.

    Intended and documented (spec 6.1; DSPX-1561 decisions, "Default key and
    payload-key assertions"): a configured default key applies to every
    assertion without a per-ID key, so the payload-key ``system-metadata``
    assertion that Java writers always add fails under an RS256 default.
    Readers that need both configure per-ID keys instead. The cases above that
    drop writer-added assertions test the default key itself; this one pins
    what happens to a Java-written TDF as it is.

    The control reads the same file with an empty keys file, under which
    ``system-metadata`` falls back to the payload key.
    """
    skip_unless(encrypt_sdk, decrypt_sdk, in_focus, "assertion_header_key_pinning")
    if encrypt_sdk.sdk != "java":
        pytest.skip("only Java writers add a payload-key system-metadata assertion")
    ct = plain_ct()
    written = [a.get("id") for a in tdfs.manifest_json(ct).get("assertions") or []]
    assert written == ["system-metadata"], written
    decrypts(
        decrypt_sdk,
        ct,
        encrypted_tdf.rt_file(ct, decrypt_sdk, "no-keys"),
        pt_file,
        verification_file(tmp_dir, "empty"),
    )
    out = fails_with(
        decrypt_sdk,
        ct,
        encrypted_tdf.rt_file(ct, decrypt_sdk, "default-key"),
        "algorithm-mismatch",
        verification_file(
            tmp_dir, "default-only-RS256", default=("RS256", authorized.public_pem)
        ),
    )
    assert b"system-metadata" in out, "the failure should name system-metadata"


def test_hmac_keyed_with_rsa_public_key(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    keyed_ct: Callable[[], Path],
    encrypted_tdf: EncryptFactory,
    pt_file: Path,
    tmp_dir: Path,
    authorized: RsaSigner,
):
    """HS256 keyed with the pinned RS256 public key PEM is refused."""
    skip_unless(encrypt_sdk, decrypt_sdk, in_focus, "assertion_header_key_pinning")
    keys = verification_file(
        tmp_dir, "per-id-rs256", keys={RS256_ID: ("RS256", authorized.public_pem)}
    )
    pem = authorized.public_pem.encode("utf-8")

    def confused(m: dict[str, Any]) -> list[Any]:
        a = bind(m, unbound(writer_assertion(m, RS256_ID)), pem, alg="HS256")
        check_signed_by(m, a, assertions.VerificationKey("HS256", pem))
        assert predict(m, a, authorized.key) == "algorithm-mismatch"
        return [a]

    def writer_signed(m: dict[str, Any]) -> list[Any]:
        return [writer_assertion(m, RS256_ID)]

    control = with_assertions(keyed_ct(), "rs256-only", writer_signed)
    decrypts(
        decrypt_sdk, control, encrypted_tdf.rt_file(control, decrypt_sdk), pt_file, keys
    )
    ct = with_assertions(keyed_ct(), "hs256-keyed-with-pem", confused)
    fails_with(
        decrypt_sdk,
        ct,
        encrypted_tdf.rt_file(ct, decrypt_sdk),
        "algorithm-mismatch",
        keys,
    )
