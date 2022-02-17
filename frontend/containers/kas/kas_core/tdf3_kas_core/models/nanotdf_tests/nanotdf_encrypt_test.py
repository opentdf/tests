import itertools
import pytest
import uuid

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidTag

from tdf3_kas_core.models.nanotdf import (
    SymmetricAndPayloadConfig,
    ECCMode,
    CurveMode,
    CipherMode,
)
from tdf3_kas_core.models.nanotdf_tests import nanotdf_utils_for_testonly as nanotdf

from tdf3_kas_core.models.nanotdf.crypto import flags

TEST_PUBLIC_KEY_BYTES = (
    b"\x035\x9a\x8co\x9c\x89\xcd`u\x08~\xb4Me\x98\x91\xe0*mZtsN \xfc?<\xa7V\x90n\xee"
)
TEST_PRIVATE_KEY_BYTES = b'0\x81\x84\x02\x01\x000\x10\x06\x07*\x86H\xce=\x02\x01\x06\x05+\x81\x04\x00\n\x04m0k\x02\x01\x01\x04 \x82\x18\x96\xd5\x157\x1c\x8a\xf7\xcf\xc5\xc9\xd3\x92 \xddTpkpd\\\x18\xd7\xe0t\x8aQ\xfd\x02"\x92\xa1D\x03B\x00\x045\x9a\x8co\x9c\x89\xcd`u\x08~\xb4Me\x98\x91\xe0*mZtsN \xfc?<\xa7V\x90n\xee\x8do\xefC6\xadk"u\xe3\xbdw\xb4N%\xe5\x93C\x1byq\x8f\xc34\x1d\x10,\xc7r\xe7sU'

test_data = [
    (
        ec.SECP256K1,
        ec.SECP256K1,
        ECCMode(True, CurveMode.SECP256K1),
        SymmetricAndPayloadConfig(
            True, CurveMode.SECP256K1, CipherMode.AES_256_GCM_TAG64
        ),
    ),
    (
        ec.SECP256R1,
        ec.SECP256R1,
        ECCMode(True, CurveMode.SECP256R1),
        SymmetricAndPayloadConfig(
            True, CurveMode.SECP256R1, CipherMode.AES_256_GCM_TAG64
        ),
    ),
    (
        ec.SECP384R1,
        ec.SECP384R1,
        ECCMode(True, CurveMode.SECP384R1),
        SymmetricAndPayloadConfig(
            True, CurveMode.SECP384R1, CipherMode.AES_256_GCM_TAG64
        ),
    ),
    (
        ec.SECP521R1,
        ec.SECP521R1,
        ECCMode(True, CurveMode.SECP521R1),
        SymmetricAndPayloadConfig(
            True, CurveMode.SECP521R1, CipherMode.AES_256_GCM_TAG64
        ),
    ),
    (
        ec.SECP521R1,
        ec.SECP521R1,
        ECCMode(True, CurveMode.SECP521R1),
        SymmetricAndPayloadConfig(
            True, CurveMode.SECP521R1, CipherMode.AES_256_GCM_TAG96
        ),
    ),
    (
        ec.SECP521R1,
        ec.SECP521R1,
        ECCMode(True, CurveMode.SECP521R1),
        SymmetricAndPayloadConfig(
            True, CurveMode.SECP521R1, CipherMode.AES_256_GCM_TAG104
        ),
    ),
    (
        ec.SECP521R1,
        ec.SECP521R1,
        ECCMode(True, CurveMode.SECP521R1),
        SymmetricAndPayloadConfig(
            True, CurveMode.SECP521R1, CipherMode.AES_256_GCM_TAG112
        ),
    ),
    (
        ec.SECP521R1,
        ec.SECP521R1,
        ECCMode(True, CurveMode.SECP521R1),
        SymmetricAndPayloadConfig(
            True, CurveMode.SECP521R1, CipherMode.AES_256_GCM_TAG120
        ),
    ),
    (
        ec.SECP521R1,
        ec.SECP521R1,
        ECCMode(True, CurveMode.SECP521R1),
        SymmetricAndPayloadConfig(
            True, CurveMode.SECP521R1, CipherMode.AES_256_GCM_TAG128
        ),
    ),
    (
        ec.SECP521R1,
        ec.SECP256R1,
        ECCMode(True, CurveMode.SECP521R1),
        SymmetricAndPayloadConfig(
            True, CurveMode.SECP256R1, CipherMode.AES_256_GCM_TAG128
        ),
    ),
]


@pytest.fixture
def allow_small_iv():
    old_value = flags["allow_small_iv"]

    def change_f(v):
        flags["allow_small_iv"] = v

    yield change_f
    flags["allow_small_iv"] = old_value


@pytest.mark.parametrize(
    "recipient_curve,signer_curve,ecc_mode," "sym_and_pay_config", test_data
)
def test_encrypt(
    recipient_curve, signer_curve, ecc_mode, sym_and_pay_config, allow_small_iv
):
    signer_private_key_bytes, signer_public_key_bytes = nanotdf.create_key_pair(
        signer_curve
    )
    private_key_bytes, public_key_bytes = nanotdf.create_key_pair(recipient_curve)

    random_string = str(uuid.uuid4()).encode("utf-8")

    # Skew testing. The idea here is that we can support decoding
    # nanotdfs encoded with 'old world' encryption, but the reverse is
    # not true, and when we disable old world creation, we should see errors
    # as well.
    allow_small_iv(False)

    # Public key, directory, policy
    tdf = nanotdf.create(
        "https://kas.virtru.com",
        "https://kas.virtru.com/policy/abcdef",
        public_key_bytes,
        random_string,
        ecc_mode=ecc_mode,
        payload_iv=b"\0\0\1",
        sym_and_pay_config=sym_and_pay_config,
        signer_private=signer_private_key_bytes,
    )

    result = nanotdf.read(tdf, private_key_bytes)
    assert result == random_string

    tdf_bytes = tdf.serialize()
    print(tdf_bytes)

    result = nanotdf.reads(tdf_bytes, private_key_bytes)
    assert result == random_string

    flags["allow_small_iv"] = True
    with pytest.raises(InvalidTag):
        nanotdf.reads(tdf_bytes, private_key_bytes)


@pytest.mark.parametrize(
    "recipient_curve,signer_curve,ecc_mode," "sym_and_pay_config", test_data
)
def test_encrypt_legacy_to_new(
    recipient_curve, signer_curve, ecc_mode, sym_and_pay_config, allow_small_iv
):
    signer_private_key_bytes, signer_public_key_bytes = nanotdf.create_key_pair(
        signer_curve
    )
    private_key_bytes, public_key_bytes = nanotdf.create_key_pair(recipient_curve)

    random_string = str(uuid.uuid4()).encode("utf-8")

    # Skew testing. The idea here is that we can support decoding
    # nanotdfs encoded with 'old world' encryption, but the reverse is
    # not true, and when we disable old world creation, we should see errors
    # as well.
    allow_small_iv(True)

    # Public key, directory, policy
    tdf = nanotdf.create(
        "https://kas.virtru.com",
        "https://kas.virtru.com/policy/abcdef",
        public_key_bytes,
        random_string,
        ecc_mode=ecc_mode,
        payload_iv=b"\0\0\1",
        sym_and_pay_config=sym_and_pay_config,
        signer_private=signer_private_key_bytes,
    )

    result = nanotdf.read(tdf, private_key_bytes)
    assert result == random_string

    tdf_bytes = tdf.serialize()
    print(tdf_bytes)

    result = nanotdf.reads(tdf_bytes, private_key_bytes)
    assert result == random_string

    flags["allow_small_iv"] = False
    with pytest.raises(InvalidTag):
        nanotdf.reads(tdf_bytes, private_key_bytes)
