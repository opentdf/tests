import bitstruct
from tdf3_kas_core.errors import NanoTDFParseError
from .crypto import CurveMode, MODE_OPTIONS


class ECCMode(object):
    @classmethod
    def parse(cls, data: bytes) -> ("ECCMode", bytes):
        ecc_mode_byte = data[0:1]
        parse_result = bitstruct.unpack("b1p4u3", ecc_mode_byte)
        if len(parse_result) != 2:
            raise NanoTDFParseError("Invalid TDF")

        use_ecdsa_binding, ecc_params = parse_result

        return (cls(use_ecdsa_binding, CurveMode(ecc_params)), data[1:])

    def __init__(self, use_ecdsa_binding: bool, params: CurveMode):
        self._use_ecdsa_binding = use_ecdsa_binding
        self._params = params

    @property
    def use_ecdsa_binding(self):
        return self._use_ecdsa_binding

    @property
    def params(self):
        return self._params

    @property
    def signature_length(self):
        return MODE_OPTIONS[self._params].signature_byte_length

    @property
    def public_key_length(self):
        return MODE_OPTIONS[self._params].public_key_byte_length

    @property
    def curve(self):
        return MODE_OPTIONS[self._params]

    def serialize(self):
        return bitstruct.pack("b1u7", self._use_ecdsa_binding, self._params.value)
