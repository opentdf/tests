import bitstruct

from tdf3_kas_core.errors import NanoTDFParseError
from .crypto import flags, CipherMode, CurveMode, MODE_OPTIONS, SYM_OPTIONS


class SymmetricAndPayloadConfig(object):
    @classmethod
    def parse(cls, data: bytes) -> ("SymmetricAndPayloadConfig", bytes):
        config_byte = data[0:1]
        parse_result = bitstruct.unpack("b1u3u4", config_byte)
        if len(parse_result) != 3:
            raise NanoTDFParseError("Invalid TDF")

        has_signature, signature_ecc_mode, symmetric_cipher = parse_result

        return (
            cls(
                has_signature,
                CurveMode(signature_ecc_mode),
                CipherMode(symmetric_cipher),
            ),
            data[1:],
        )

    def __init__(
        self, has_signature: bool, signature_ecc_mode: int, symmetric_cipher: int
    ):
        self._has_signature = has_signature
        self._signature_ecc_mode = signature_ecc_mode
        self._symmetric_cipher_mode = symmetric_cipher

    @property
    def has_signature(self) -> bool:
        return self._has_signature

    @property
    def symmetric_cipher_mode(self) -> CipherMode:
        return self._symmetric_cipher_mode

    @property
    def signature_ecc_mode(self) -> CurveMode:
        return self._signature_ecc_mode

    @property
    def signature_length(self):
        return MODE_OPTIONS[self._signature_ecc_mode].signature_byte_length

    @property
    def curve(self):
        return MODE_OPTIONS[self._signature_ecc_mode]

    @property
    def public_key_length(self):
        return MODE_OPTIONS[self._signature_ecc_mode].public_key_byte_length

    @property
    def symmetric_tag_length(self):
        return SYM_OPTIONS[self._symmetric_cipher_mode].tag_length

    def symmetric_cipher(self, key: bytes, iv: bytes = b"\x00" * 12):
        return SYM_OPTIONS[self._symmetric_cipher_mode](key, iv)

    def serialize(self):
        return bitstruct.pack(
            "b1u3u4",
            self._has_signature,
            self._signature_ecc_mode.value,
            self._symmetric_cipher_mode.value,
        )
