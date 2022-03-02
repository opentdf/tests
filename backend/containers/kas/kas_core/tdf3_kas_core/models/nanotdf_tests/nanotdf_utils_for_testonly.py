from typing import Optional
import bitstruct
import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

from tdf3_kas_core.models.nanotdf.crypto import flags

from tdf3_kas_core.errors import NanoTDFParseError
from tdf3_kas_core.models.nanotdf import (
    Signature,
    NanoTDF,
    SymmetricAndPayloadConfig,
    Policy,
    ByteData,
    Header,
    ECCMode,
    Payload,
    ResourceLocator,
    ResourceDirectory,
    CurveMode,
    PolicyType,
    create_resource_locator,
    CipherMode,
)


def loads(data: bytes):
    magic_number_and_version = data[0:3]
    data = data[3:]

    if len(magic_number_and_version) != 3:
        raise NanoTDFParseError("Invalid TDF")

    version_parse_result = bitstruct.unpack("u8u8u2u6", magic_number_and_version)

    if len(version_parse_result) != 4:
        raise NanoTDFParseError("Invalid TDF")

    _, _, _, version = version_parse_result

    if version != 12:
        raise NanoTDFParseError(
            "This client does not handle nanotdf version %d" % version
        )

    # Parse Header
    header, data = load_header(data)

    # Parse Payload
    payload, data = load_payload(header.symmetric_and_payload_config, data)

    signature, data = Signature.parse(header, data)

    return NanoTDF(header, payload, signature)


def load_header(data: bytes):
    # Parse KAS Header
    kas, data = load_resource_locator(data)
    ecc_mode, data = load_ecc_mode(data)
    sym_and_pay, data = SymmetricAndPayloadConfig.parse(data)
    policy, data = Policy.parse(ecc_mode, sym_and_pay, data)
    key, data = ByteData.parse_with_content_length(ecc_mode.public_key_length, data)

    header = Header(
        kas,
        ecc_mode,
        sym_and_pay,
        policy,
        key,
    )
    return (header, data)


def load_payload(config: SymmetricAndPayloadConfig, data: bytes):
    return Payload.parse(config, data)


def load_ecc_mode(data: bytes) -> (ECCMode, bytes):
    return ECCMode.parse(data)


def load_resource_locator(data: bytes) -> (ResourceLocator, bytes):
    return ResourceLocator.parse(data)


def create(
    kas_url: str,
    policy_url: str,
    receiver_public_key: bytes,
    plaintext: bytes,
    payload_iv: bytes,
    ecc_mode: Optional[ECCMode] = None,
    sym_and_pay_config: Optional[SymmetricAndPayloadConfig] = None,
    signer_private: Optional[bytes] = None,
    directory: Optional[ResourceDirectory] = None,
) -> bytes:
    kas = create_resource_locator(kas_url, directory)
    if not ecc_mode:
        ecc_mode = ECCMode(True, CurveMode.SECP256R1)
    if not sym_and_pay_config:
        sym_and_pay_config = SymmetricAndPayloadConfig(
            False, CurveMode.SECP256R1, CipherMode.AES_256_GCM_TAG64
        )

    if sym_and_pay_config.has_signature and not signer_private:
        raise ValueError("Must have a private key to sign if the tdf has a signature")

    encryptor = ecc_mode.curve.create_encryptor(receiver_public_key)

    key = encryptor.symmetric_key

    real_iv = payload_iv if flags["allow_small_iv"] else b"\0" * 9 + payload_iv
    symmetric_cipher = sym_and_pay_config.symmetric_cipher(key, real_iv)
    ciphertext, tag = symmetric_cipher.encrypt(plaintext)

    ephemeral_key = ByteData(encryptor.public_key)

    policy_locator = create_resource_locator(policy_url)
    binding = ByteData(encryptor.sign(policy_locator.serialize()))

    policy = Policy(PolicyType.REMOTE, policy_locator, binding)

    header = Header(
        kas,
        ecc_mode,
        sym_and_pay_config,
        policy,
        ephemeral_key,
    )

    payload = Payload(payload_iv, ciphertext, tag)

    if sym_and_pay_config.has_signature:
        signer = sym_and_pay_config.curve.create_signer(signer_private)
        signature_body = ByteData(signer.sign(header.serialize() + payload.serialize()))
        signature = Signature(ByteData(signer.public_key), signature_body)
    else:
        signature, _ = ByteData.parse_with_content_length(0, b"")

    return NanoTDF(header, payload, signature)


def read(
    tdf: NanoTDF, private_key: bytes, directory: Optional[ResourceDirectory] = None
) -> bytes:
    # TODO fix names in this function... it's a bit messy
    payload_iv = tdf.payload.iv
    decryptor = tdf.header.ecc_mode.curve.create_decryptor(
        tdf.header.key.data, private_key
    )
    key = decryptor.symmetric_key
    real_iv = payload_iv if flags["allow_small_iv"] else b"\0" * 9 + payload_iv
    symmetric_cipher = tdf.header.symmetric_and_payload_config.symmetric_cipher(
        key, real_iv
    )

    binding_bytes = tdf.header.policy.binding.data
    policy_body = tdf.header.policy.body

    decryptor.verify(binding_bytes, policy_body.serialize())

    if tdf.header.symmetric_and_payload_config.has_signature:
        verifier = tdf.header.symmetric_and_payload_config.curve.create_verifier(
            tdf.signature.public_key.data
        )
        verifier.verify(
            tdf.signature.signature_body.data,
            tdf.header.serialize() + tdf.payload.serialize(),
        )

    return symmetric_cipher.decrypt(tdf.payload.body, tdf.payload.tag)


def reads(
    tdf_bytes: bytes, private_key: bytes, directory: Optional[ResourceDirectory] = None
) -> bytes:
    return read(loads(tdf_bytes), private_key, directory)


def create_key_pair(curve) -> (bytes, bytes):
    private_key = ec.generate_private_key(curve(), default_backend())
    private_key_bytes = private_key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_key_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint
    )
    return (private_key_bytes, public_key_bytes)
