import struct
from .locator import ResourceLocator
from .data import ByteData
from .symconfig import SymmetricAndPayloadConfig
from .eccbinding import ECCMode
from enum import Enum


class PolicyType(Enum):
    REMOTE = 0
    PLAINTEXT = 1
    ENCRYPTED = 2
    ENCRYPTED_WITH_POLICY_ACCESS = 3


def remote_policy_parser(data: bytes) -> (ResourceLocator, bytes):
    return ResourceLocator.parse(data)


def byte_data(data: bytes) -> (ByteData, bytes):
    return ByteData.parse(2, data)


def remote_policy_serializer(locator: ResourceLocator) -> bytes:
    return locator.serialize()


def byte_data_serializer(data: ByteData) -> bytes:
    return data.serialize_with_content_length(2)


class Policy(object):
    GMAC_TAG_LENGTH = 8
    body_parsers = {
        PolicyType.REMOTE: remote_policy_parser,
        PolicyType.PLAINTEXT: byte_data,
        PolicyType.ENCRYPTED: byte_data,
    }

    body_serializers = {
        PolicyType.REMOTE: remote_policy_serializer,
        PolicyType.PLAINTEXT: byte_data_serializer,
        PolicyType.ENCRYPTED: byte_data_serializer,
    }

    @classmethod
    def parse(
        cls,
        ecc_mode: ECCMode,
        sym_and_payl_config: SymmetricAndPayloadConfig,
        data: bytes,
    ) -> ("Policy", bytes):
        # Parse type
        policy_type = PolicyType(struct.unpack("!B", data[0:1])[0])

        data = data[1:]

        # Depending on type parse the body
        body, data = cls.body_parsers[policy_type](data)

        binding_length = ecc_mode.signature_length
        if ecc_mode.use_ecdsa_binding is False:
            binding_length = cls.GMAC_TAG_LENGTH

        binding, data = ByteData.parse_with_content_length(binding_length, data)

        # load the binding
        return (cls(policy_type, body, binding), data)

    def __init__(self, type: PolicyType, body, binding: ByteData):
        self._type = type
        self._body = body
        self._binding = binding

    @property
    def type(self):
        return self._type

    @property
    def body(self):
        return self._body

    @property
    def binding(self):
        return self._binding

    def serialize(self):
        serialized_body = self.body_serializers[self._type](self._body)
        serialized_binding = self.binding.serialize()

        return b"%s%s%s" % (
            struct.pack("!B", self._type.value),
            serialized_body,
            serialized_binding,
        )
