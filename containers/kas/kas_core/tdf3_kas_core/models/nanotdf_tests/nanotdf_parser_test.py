from tdf3_kas_core.models.nanotdf import (
    CurveMode,
    PolicyType,
    ResourceProtocol,
    CipherMode,
)
from tdf3_kas_core.models.nanotdf_tests import (
    basic,
    plainpolicy,
    nanotdf_utils_for_testonly as nanotdf,
)


def test_basic_load_and_serialize():
    tdf = nanotdf.loads(basic.NANOTDF)
    assert tdf.header is not None

    assert tdf.header.kas.data == b"\x00"
    assert tdf.header.kas.mode == ResourceProtocol.Directory

    assert tdf.header.ecc_mode.use_ecdsa_binding == True
    assert tdf.header.ecc_mode.params == CurveMode.SECP256R1

    assert tdf.header.symmetric_and_payload_config.has_signature == True
    assert (
        tdf.header.symmetric_and_payload_config.signature_ecc_mode
        == CurveMode.SECP256R1
    )
    assert (
        tdf.header.symmetric_and_payload_config.symmetric_cipher_mode
        == CipherMode.AES_256_GCM_TAG64
    )

    assert tdf.header.policy.type == PolicyType.REMOTE
    assert tdf.header.policy.body is not None
    assert tdf.header.policy.binding.len() == 64

    assert tdf.header.key.len() == 33

    assert tdf.payload.iv == b"\x00\x00\x01"
    assert len(tdf.payload.body) == 5
    assert len(tdf.payload.tag) == 8

    assert len(tdf.signature.serialize()) == 64 + 33

    assert tdf.serialize() == basic.NANOTDF


def test_plaintext_load_and_serialize():
    tdf = nanotdf.loads(plainpolicy.NANOTDF)
    assert tdf.header is not None

    assert tdf.header.kas.data == b"\x00"
    assert tdf.header.kas.mode == ResourceProtocol.Directory

    assert tdf.header.ecc_mode.use_ecdsa_binding == True
    assert tdf.header.ecc_mode.params == CurveMode.SECP256R1

    assert tdf.header.symmetric_and_payload_config.has_signature == False
    assert (
        tdf.header.symmetric_and_payload_config.signature_ecc_mode
        == CurveMode.SECP256R1
    )
    assert (
        tdf.header.symmetric_and_payload_config.symmetric_cipher_mode
        == CipherMode.AES_256_GCM_TAG64
    )

    assert tdf.header.policy.type == PolicyType.PLAINTEXT
    assert tdf.header.policy.body.data == b"\xff\xff"
    assert tdf.header.policy.binding.len() == 64

    assert tdf.header.key.len() == 33

    assert tdf.payload.iv == b"\x00\x00\x01"
    assert len(tdf.payload.body) == 5
    assert len(tdf.payload.tag) == 8

    assert len(tdf.signature.serialize()) == 0

    assert tdf.serialize() == plainpolicy.NANOTDF


def test_serialize_resource_locator():
    locator = nanotdf.ResourceLocator(ResourceProtocol.Directory, b"ABCDEF")
    assert locator.serialize() == b"\xff\x06ABCDEF"


def test_parse_and_use_resource_locator():
    directory = nanotdf.ResourceDirectory(
        {0: "https://kas.virtru.com", 1: "https://kas.virtru.com/policy"}
    )
    locator, _data = nanotdf.ResourceLocator.parse(b"\xff\x12\x01/some/path/in/url")

    url = locator.resolve(directory)
    assert url == "https://kas.virtru.com/policy/some/path/in/url"


def test_resource_locator_factory():
    directory = nanotdf.ResourceDirectory(
        {0: "https://kas.virtru.com", 1: "https://kas.virtru.com/policy"}
    )
    locator1 = nanotdf.create_resource_locator("https://example.com", directory)
    locator2 = nanotdf.create_resource_locator(
        "https://kas.virtru.com/something/different", directory
    )
    assert locator1.serialize() == b"\x01\x0bexample.com"
    assert locator2.serialize() == b"\xff\x15\x00/something/different"


def test_serialize_ecc_mode():
    ecc_mode = nanotdf.ECCMode(True, CurveMode(2))
    assert ecc_mode.serialize() == b"\x82"


def test_serialize_symmetric_and_payload_config():
    spc = nanotdf.SymmetricAndPayloadConfig(True, CurveMode(1), CipherMode(2))
    assert spc.serialize() == b"\x92"


def test_serialize_byte_data():
    data = nanotdf.ByteData(b"abcdef")

    assert data.serialize() == b"abcdef"
    assert data.serialize_with_content_length(3) == b"\x00\x00\x06abcdef"


def test_serialize_policy():
    locator = nanotdf.ResourceLocator(ResourceProtocol.Directory, b"abcdef")
    binding = nanotdf.ByteData(b"123456")
    policy = nanotdf.Policy(PolicyType.REMOTE, locator, binding)

    assert policy.serialize() == b"\x00\xff\x06abcdef123456"


def test_serialize_payload():
    payload = nanotdf.Payload(b"\x00\x00\x01", b"abcdef", b"01234567")

    assert payload.serialize() == b"\x00\x00\x11\x00\x00\x01abcdef01234567"

    parsed, _ = nanotdf.Payload.parse(
        nanotdf.SymmetricAndPayloadConfig(True, CurveMode(1), CipherMode(0)),
        payload.serialize(),
    )

    print(parsed.serialize())
    assert payload.serialize() == parsed.serialize()
