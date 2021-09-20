import struct
from .data import ByteData
from .symconfig import SymmetricAndPayloadConfig


class Payload(object):
    @classmethod
    def parse(
        cls, config: SymmetricAndPayloadConfig, data: bytes
    ) -> ("Payload", bytes):
        # Add a 1 byte padding to get struct to parse the big endian number
        body, data = ByteData.parse(3, data)

        iv = body.data[0:3]

        ciphertext = body.data[3 : -config.symmetric_tag_length]

        auth_tag = body.data[-config.symmetric_tag_length :]

        return (cls(iv, ciphertext, auth_tag), data)

    def __init__(self, iv: bytes, ciphertext: bytes, auth_tag: bytes):
        if len(iv) != 3:
            raise ValueError("iv must be 3 bytes")

        if iv == "\x00\x00\x00":
            raise ValueError("iv must not be zero")

        self._iv = iv
        self._ciphertext = ciphertext
        self._auth_tag = auth_tag

    @property
    def iv(self):
        return self._iv

    @property
    def body(self):
        return self._ciphertext

    @property
    def tag(self):
        return self._auth_tag

    def serialize(self):
        return ByteData(self.iv + self.body + self.tag).serialize_with_content_length(3)
