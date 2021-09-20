from typing import Optional
from .header import Header
from .payload import Payload
from .data import ByteData


class NanoTDF(object):
    def __init__(
        self, header: Header, payload: Payload, signature: Optional[ByteData] = None
    ):
        self._header = header
        self._payload = payload
        self._signature = signature

    @property
    def header(self) -> Header:
        return self._header

    @property
    def payload(self) -> Payload:
        return self._payload

    @property
    def signature(self) -> ByteData:
        return self._signature

    def serialize(self):
        return b"%s%s%s" % (
            self.header.serialize(),
            self.payload.serialize(),
            self.signature.serialize(),
        )
