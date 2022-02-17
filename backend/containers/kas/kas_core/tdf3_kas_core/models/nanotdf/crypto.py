"""
List the modes of crypto and the methods used to do the cryptography.
"""

import logging
import math
import os
from enum import Enum

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


logger = logging.getLogger(__name__)


def version_salt():
    digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
    digest.update(b"L1L")
    return digest.finalize()


DEFAULT_SALT = version_salt()


# NOTE(PLAT-1172) Enable compatibility mode for older wrapped keys.
# TODO(PLAT-1212) Set this value to False & remove code.
flags = {
    "allow_small_iv": os.environ.get("LEGACY_NANOTDF_IV") == "1",
}


class CipherMode(Enum):
    AES_256_GCM_TAG64 = 0
    AES_256_GCM_TAG96 = 1
    AES_256_GCM_TAG104 = 2
    AES_256_GCM_TAG112 = 3
    AES_256_GCM_TAG120 = 4
    AES_256_GCM_TAG128 = 5


class SymmetricCipher(object):
    tag_length = None

    def __init__(self, key: bytes, iv: bytes):
        self._key = key
        valid_length = True
        if flags["allow_small_iv"]:
            valid_length = 3 <= len(iv) <= 128
        else:
            valid_length = 12 == len(iv)
        if not valid_length:
            raise ValueError(f"Invalid length for i.v., [{len(iv)}]")
        self._iv = iv

    def encrypt(self, plaintext: bytes) -> (bytes, bytes):
        raise NotImplementedError("must implement encrypt")

    def decrypt(self, ciphertext: bytes, tag: bytes) -> bytes:
        raise NotImplementedError("must implement decrypt")


class GCMCipher(SymmetricCipher):
    def encrypt(self, plaintext: bytes) -> bytes:
        algorithm = algorithms.AES(self._key)
        if flags["allow_small_iv"]:
            # NOTE(PLAT-1166) Force small i.v. in cryptography 3.3+
            cipher = Cipher(
                algorithm,
                modes.GCM(b"0123456789AB"),
                backend=default_backend(),
            )
            cipher.mode._initialization_vector = self._iv
        else:
            cipher = Cipher(
                algorithm,
                modes.GCM(self._iv),
                backend=default_backend(),
            )

        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        return (ciphertext, encryptor.tag[0 : self.tag_length])

    def decrypt(self, ciphertext: bytes, tag: bytes) -> bytes:
        algorithm = algorithms.AES(self._key)
        if flags["allow_small_iv"]:
            # NOTE(PLAT-1166) Force small i.v. in cryptography 3.3+
            cipher = Cipher(
                algorithm,
                modes.GCM(b"BA9876543210", tag, self.tag_length),
                backend=default_backend(),
            )
            cipher.mode._initialization_vector = self._iv
        else:
            cipher = Cipher(
                algorithm,
                modes.GCM(self._iv, tag, self.tag_length),
                backend=default_backend(),
            )

        decryptor = cipher.decryptor()
        return decryptor.update(ciphertext) + decryptor.finalize()


class CurveMode(Enum):
    SECP256R1 = 0
    SECP384R1 = 1
    SECP521R1 = 2
    SECP256K1 = 3

    # Curve25519 doesn't work and may never work but research needs to be done.
    Curve25519 = 4


class Encryptor(object):
    key_alg = ec.SECP256K1

    @classmethod
    def create_signer(cls, curve: "Curve", private_key_bytes: bytes):
        private_key = serialization.load_der_private_key(
            private_key_bytes, None, backend=default_backend()
        )

        public_key_bytes = private_key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint
        )

        return cls(curve, public_key_bytes, b"", private_key)

    @classmethod
    def create(cls, curve: "Curve", receiver_public_key_bytes: bytes):
        private_key = ec.generate_private_key(cls.key_alg(), default_backend())
        public_key_bytes = private_key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint
        )
        receiver_public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            cls.key_alg(), receiver_public_key_bytes
        )
        shared_key = private_key.exchange(ec.ECDH(), receiver_public_key)

        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=DEFAULT_SALT,
            info=None,
            backend=default_backend(),
        ).derive(shared_key)

        return cls(curve, public_key_bytes, derived_key, private_key)

    def __init__(
        self, curve: "Curve", public_key: bytes, symmetric_key: bytes, private_key
    ):
        self._curve = curve
        self._public_key = public_key
        self._symmetric_key = symmetric_key
        self._private_key = private_key

    @property
    def symmetric_key(self):
        return self._symmetric_key

    @property
    def public_key(self) -> bytes:
        return self._public_key

    def sign(self, data_to_sign: bytes) -> bytes:
        der_encoded_signature = self._private_key.sign(
            data_to_sign, ec.ECDSA(hashes.SHA256())
        )

        signature_r, signature_s = decode_dss_signature(der_encoded_signature)

        return b"%s%s" % (
            signature_r.to_bytes(self._curve.byte_length, byteorder="big"),
            signature_s.to_bytes(self._curve.byte_length, byteorder="big"),
        )

    def public_key_as_pem(self):
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            self.key_alg(), self._public_key
        )
        return public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )


class Decryptor(object):
    key_alg = ec.SECP256K1

    @classmethod
    def create(
        cls, curve: "Curve", ephemeral_public_key_bytes: bytes, private_key_bytes: bytes
    ):
        private_key = serialization.load_der_private_key(
            private_key_bytes, None, backend=default_backend()
        )

        ephemeral_public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            cls.key_alg(), ephemeral_public_key_bytes
        )
        shared_key = private_key.exchange(ec.ECDH(), ephemeral_public_key)

        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=DEFAULT_SALT,
            info=None,
            backend=default_backend(),
        ).derive(shared_key)

        return cls(curve, private_key, ephemeral_public_key, derived_key)

    @classmethod
    def create_verifier(cls, curve: "Curve", public_key_bytes: bytes):
        ephemeral_public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            cls.key_alg(), public_key_bytes
        )
        return cls(curve, b"", ephemeral_public_key, b"")

    def __init__(
        self, curve: "Curve", private_key, ephemeral_public, symmetric_key: bytes
    ):
        self._curve = curve
        self._private_key = private_key
        self._ephemeral_public = ephemeral_public
        self._symmetric_key = symmetric_key

    @property
    def symmetric_key(self) -> bytes:
        return self._symmetric_key

    def verify(self, signature: bytes, data_to_sign: bytes):
        assert (
            len(signature) == self._curve.signature_byte_length
        ), "should have expected signature length"

        # Pull r,s out of signature
        signature_r = int.from_bytes(
            signature[0 : self._curve.byte_length], byteorder="big"
        )
        signature_s = int.from_bytes(
            signature[self._curve.byte_length : self._curve.byte_length * 2],
            byteorder="big",
        )

        der_encoded_signature = encode_dss_signature(signature_r, signature_s)

        return self._ephemeral_public.verify(
            der_encoded_signature,
            data_to_sign,
            signature_algorithm=ec.ECDSA(hashes.SHA256()),
        )


class Curve(object):
    """
    Generic class that defines a curve
    """

    bit_length = 256
    pad = 1
    encryptor_cls = Encryptor
    decryptor_cls = Decryptor

    def create_encryptor(self, public_key: bytes) -> Encryptor:
        return self.encryptor_cls.create(self, public_key)

    def create_decryptor(
        self, ephemeral_public: bytes, private_key: bytes
    ) -> Decryptor:
        return self.decryptor_cls.create(self, ephemeral_public, private_key)

    def create_verifier(self, public_key: bytes) -> Decryptor:
        return self.decryptor_cls.create_verifier(self, public_key)

    def create_signer(self, private_key: bytes) -> Encryptor:
        return self.encryptor_cls.create_signer(self, private_key)

    @property
    def byte_length(self) -> int:
        return int(math.ceil(self.bit_length / 8.0))

    @property
    def signature_byte_length(self) -> int:
        return self.byte_length * 2

    # This assumes that the public key is
    @property
    def public_key_byte_length(self) -> int:
        return self.byte_length + self.pad


class CurveSECP256K1Encryptor(Encryptor):
    pass


class CurveSECP256K1Decryptor(Decryptor):
    pass


class CurveSECP256R1Encryptor(Encryptor):
    key_alg = ec.SECP256R1


class CurveSECP256R1Decryptor(Decryptor):
    key_alg = ec.SECP256R1


class CurveSECP384R1Encryptor(Encryptor):
    key_alg = ec.SECP384R1


class CurveSECP384R1Decryptor(Decryptor):
    key_alg = ec.SECP384R1


class CurveSECP521R1Encryptor(Encryptor):
    key_alg = ec.SECP521R1


class CurveSECP521R1Decryptor(Decryptor):
    key_alg = ec.SECP521R1


class CurveSECP256K1(Curve):
    bit_length = 256

    encryptor_cls = CurveSECP256K1Encryptor
    decryptor_cls = CurveSECP256K1Decryptor


class Curve25519(Curve):
    bit_length = 256
    pad = 0


class CurveSECP256R1(Curve):
    bit_length = 256

    encryptor_cls = CurveSECP256R1Encryptor
    decryptor_cls = CurveSECP256R1Decryptor


class CurveSECP384R1(Curve):
    bit_length = 384

    encryptor_cls = CurveSECP384R1Encryptor
    decryptor_cls = CurveSECP384R1Decryptor


class CurveSECP521R1(Curve):
    bit_length = 521

    encryptor_cls = CurveSECP521R1Encryptor
    decryptor_cls = CurveSECP521R1Decryptor


MODE_OPTIONS = {
    CurveMode.SECP256R1: CurveSECP256R1(),
    CurveMode.SECP384R1: CurveSECP384R1(),
    CurveMode.SECP521R1: CurveSECP521R1(),
    CurveMode.SECP256K1: CurveSECP256K1(),
    CurveMode.Curve25519: Curve25519(),
}


def gcm_factory(length):
    class _GCMCipher(GCMCipher):
        tag_length = length

    return _GCMCipher


SYM_OPTIONS = {
    CipherMode.AES_256_GCM_TAG64: gcm_factory(8),
    CipherMode.AES_256_GCM_TAG96: gcm_factory(12),
    CipherMode.AES_256_GCM_TAG104: gcm_factory(13),
    CipherMode.AES_256_GCM_TAG112: gcm_factory(14),
    CipherMode.AES_256_GCM_TAG120: gcm_factory(15),
    CipherMode.AES_256_GCM_TAG128: gcm_factory(16),
}
