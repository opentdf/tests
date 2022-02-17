"""
Wrapper class for bytes of data.
"""

import struct


class ByteData(object):
    @classmethod
    def parse(cls, length_bytes: int, data: bytes) -> ("ByteData", bytes):
        size_str = data[0:length_bytes]

        if length_bytes > 4:
            raise ValueError(
                "ByteData does not support a content length longer than 4 bytes"
            )
        padding_length = 4 - length_bytes
        padded_size_str = b"%s%s" % (b"\x00" * padding_length, size_str)
        size = struct.unpack("!I", padded_size_str)[0]
        return (
            cls(data[length_bytes : size + length_bytes]),
            data[size + length_bytes :],
        )

    @classmethod
    def parse_with_content_length(cls, size: int, data: bytes) -> ("ByteData", bytes):
        return (cls(data[0:size]), data[size:])

    def __init__(self, data: bytes):
        self._data = data

    @property
    def data(self) -> bytes:
        return self._data

    def len(self) -> int:
        return len(self._data)

    def serialize(self):
        return self._data

    def serialize_with_content_length(self, length_bytes: int) -> bytes:
        padded_size_str = struct.pack("!I", len(self._data))
        size_str = padded_size_str[len(padded_size_str) - length_bytes :]
        return b"%s%s" % (size_str, self._data)
