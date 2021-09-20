from .header import Header
from .policy import Policy
from .data import ByteData


class Signature(object):
    @classmethod
    def parse(cls, header: Header, data: bytes) -> ("Signature", bytes):
        signature, _ = ByteData.parse_with_content_length(0, b"")

        if not header.symmetric_and_payload_config.has_signature:
            return ByteData.parse_with_content_length(0, data)

        signature_length = header.symmetric_and_payload_config.signature_length
        public_key_length = header.symmetric_and_payload_config.public_key_length
        public_key, data = ByteData.parse_with_content_length(public_key_length, data)
        signature, data = ByteData.parse_with_content_length(signature_length, data)
        return (cls(public_key, signature), data)

    def __init__(self, public_key, signature_body):
        self._public_key = public_key
        self._signature_body = signature_body

    @property
    def signature_body(self):
        return self._signature_body

    @property
    def public_key(self):
        return self._public_key

    def serialize(self) -> bytes:
        return b"%s%s" % (
            self._public_key.serialize(),
            self._signature_body.serialize(),
        )
