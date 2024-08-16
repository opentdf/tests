import dataclasses
import itertools
import logging
import typing

from construct import (
    Array,
    BitsInteger,
    Byte,
    Bytes,
    Const,
    Flag,
    If,
    Int8ub,
    Int16ub,
    Int24ub,
    PascalString,
    this,
)
import construct
from construct_typed import (
    DataclassBitStruct,
    DataclassMixin,
    DataclassStruct,
    EnumBase,
    TEnum,
    csfield,
)
import construct_typed

logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)


def enc_hex(B: bytes) -> str:
    """Pretty print bytes as a block of hex bytes, suitable for formatting."""
    strides = [B[i * 20 : (i + 1) * 20] for i in range((len(B) + 19) // 20)]
    to_s = lambda n: hex(n)[2:].zfill(2)
    return "\n".join([" ".join(to_s(n) for n in stride) for stride in strides])


def enc_hex_w_comment(B: bytes, c: str) -> str:
    hex = enc_hex(B)
    if len(hex) < 60:
        return f"{hex} # {c}"
    return f"\n# {c}\n{hex}"


def dec_hex(hexes: str) -> bytes:
    """Read in a block of hex formatted bytes."""
    return bytes(int(n, 16) for n in hexes.split())


def dec_hex_w_comments(hexes_w_comments: str) -> bytes:
    """Read in a block of hexes, skipping hashtag comments"""
    return b"".join(
        [dec_hex(l.partition("#")[0].rstrip()) for l in hexes_w_comments.split("\n")]
    )


class UrlProtocol(EnumBase):
    HTTP = 0
    HTTPS = 1


class EccMode(EnumBase):
    secp256r1 = 0
    secp384r1 = 1
    secp521r1 = 2
    secp256k1 = 3

    @property
    def bit_length(self) -> int:
        if self in (EccMode.secp256r1, EccMode.secp256k1):
            return 256
        if self == EccMode.secp384r1:
            return 384
        if self == EccMode.secp521r1:
            return 521

    @property
    def byte_length(self) -> int:
        # return int(math.ceil(self.bit_length / 8.0))
        return (self.bit_length + 7) >> 3

    @property
    def signature_length(self) -> int:
        # return self.byte_length * 2
        return self.byte_length << 1

    @property
    def public_key_length(self) -> int:
        return self.byte_length + 1

    def __getitem__(self, key):
        return getattr(self, key)


class SymmetricCipherMode(EnumBase):
    AES_256_GCM_64 = 0
    AES_256_GCM_96 = 1
    AES_256_GCM_104 = 2
    AES_256_GCM_112 = 3
    AES_256_GCM_120 = 4
    AES_256_GCM_128 = 5

    @property
    def mac_length(self) -> int:
        """MAC length in bytes"""
        if self == SymmetricCipherMode.AES_256_GCM_64:
            return 8
        if self == SymmetricCipherMode.AES_256_GCM_96:
            return 12
        if self == SymmetricCipherMode.AES_256_GCM_104:
            return 13
        if self == SymmetricCipherMode.AES_256_GCM_112:
            return 14
        if self == SymmetricCipherMode.AES_256_GCM_120:
            return 15
        if self == SymmetricCipherMode.AES_256_GCM_128:
            return 16

    def __getitem__(self, key):
        return getattr(self, key)


class PolicyType(EnumBase):
    REMOTE = 0
    EMBEDDED = 1
    ENCRYPTED = 2
    ENCRYPTED_PKA = 3


@dataclasses.dataclass
class MagicAndVersion(DataclassMixin):
    magic: int = csfield(Const(0b0100_1100_0011_0001_01, BitsInteger(18)))
    version: int = csfield(BitsInteger(6))

    def __bytes__(self) -> bytes:
        return magic_and_version_format.build(self)


magic_and_version_format = construct_typed.DataclassBitStruct(MagicAndVersion)


@dataclasses.dataclass
class ResourceLocator(DataclassMixin):
    protocol_type: UrlProtocol = csfield(TEnum(Int8ub, UrlProtocol))
    body: bytes = csfield(PascalString(Int8ub, "utf8"))

    def __bytes__(self) -> bytes:
        return resource_locator_format.build(self)


resource_locator_format = construct_typed.DataclassStruct(ResourceLocator)


@dataclasses.dataclass
class BindingMode(DataclassMixin):
    use_ecdsa_binding: bool = csfield(Flag)
    unused: int = csfield(Const(0b0000, BitsInteger(4)))
    ecc_params: EccMode = csfield(TEnum(BitsInteger(3), EccMode))

    def __bytes__(self) -> bytes:
        return binding_mode_format.build(self)


binding_mode_format = construct_typed.DataclassBitStruct(BindingMode)


@dataclasses.dataclass
class SymmetricAndPayloadConfig(DataclassMixin):
    has_signature: bool = csfield(Flag)
    signature_ecc_mode: EccMode = csfield(TEnum(BitsInteger(3), EccMode))
    symmetric_cipher_mode: SymmetricCipherMode = csfield(
        TEnum(BitsInteger(4), SymmetricCipherMode)
    )

    def __bytes__(self) -> bytes:
        return symmetric_and_payload_config_format.build(self)


symmetric_and_payload_config_format = construct_typed.DataclassBitStruct(
    SymmetricAndPayloadConfig
)


# ??? taken from go parser but this seems wrong
@dataclasses.dataclass
class EcdsaBinding(DataclassMixin):
    length_r: int = csfield(Int8ub)
    r: bytes = csfield(Bytes(this.length_r))
    length_s: int = csfield(Int8ub)
    s: bytes = csfield(Bytes(this.length_s))


@dataclasses.dataclass
class Policy(DataclassMixin):
    policy_type: PolicyType = csfield(TEnum(Int8ub, PolicyType))

    embedded: str | None = csfield(
        If(this.policy_type == PolicyType.EMBEDDED, PascalString(Int16ub, "utf8"))
    )

    encrypted_length: int | None = csfield(
        If(
            this.policy_type == PolicyType.ENCRYPTED
            or this.policy_type == PolicyType.ENCRYPTED_PKA,
            Int16ub,
        )
    )
    encrypted: bytes | None = csfield(
        If(
            this.policy_type == PolicyType.ENCRYPTED
            or this.policy_type == PolicyType.ENCRYPTED_PKA,
            Bytes(this.encrypted_length),
        )
    )

    remote: ResourceLocator | None = csfield(
        If(this.policy_type == PolicyType.REMOTE, DataclassStruct(ResourceLocator))
    )

    def __bytes__(self) -> bytes:
        return policy_format.build(self)


policy_format = construct_typed.DataclassStruct(Policy)


def embedded_policy(embedded: str) -> Policy:
    return Policy(
        policy_type=PolicyType.EMBEDDED,
        embedded=embedded,
        encrypted_length=None,
        encrypted=None,
        remote=None,
    )


def encrypted_policy(encrypted: bytes) -> Policy:
    return Policy(
        policy_type=(PolicyType.ENCRYPTED),
        encrypted_length=len(encrypted),
        encrypted=encrypted,
        embedded=None,
        remote=None,
    )


def remote_policy(uri: ResourceLocator) -> Policy:
    return Policy(
        policy_type=PolicyType.REMOTE,
        remote=uri,
        encrypted_length=None,
        encrypted=None,
        embedded=None,
    )


@dataclasses.dataclass
class Header(DataclassMixin):
    version: MagicAndVersion = csfield(DataclassBitStruct(MagicAndVersion))
    kas: ResourceLocator = csfield(DataclassStruct(ResourceLocator))
    binding_mode: BindingMode = csfield(DataclassBitStruct(BindingMode))
    symmetric_and_payload_config: SymmetricAndPayloadConfig = csfield(
        DataclassBitStruct(SymmetricAndPayloadConfig)
    )
    policy: Policy = csfield(DataclassStruct(Policy))

    ecdsa_binding: bytes | None = csfield(
        If(this.binding_mode.use_ecdsa_binding, DataclassBitStruct(EcdsaBinding))
    )
    gmac_binding: bytes | None = csfield(
        construct.IfThenElse(this.binding_mode.use_ecdsa_binding, construct.Pass, Bytes(8))
    )

    ephemeral_key: bytes = csfield(
        Bytes(this.symmetric_and_payload_config.signature_ecc_mode.public_key_length)
    )

    def pretty(self) -> str:
        keys = [
            "version",
            "kas",
            "binding_mode",
            "symmetric_and_payload_config",
            "policy",
        ]
        if self.binding_mode.use_ecdsa_binding:
            raise ValueError("unsupported binding mode")
        if self.ecdsa_binding:
            keys += ["ecdsa_binding"]
            if self.gmac_binding:
                raise ValueError("cannot have two bindings")
            if not self.binding_mode.use_ecdsa_binding:
                raise ValueError("wrong binding mode")
        elif self.gmac_binding:
            keys += ["gmac_binding"]
        keys += ["ephemeral_key"]
        return "\n".join([enc_hex_w_comment(bytes(self[k]), k) for k in keys])


header_format = construct_typed.DataclassStruct(Header)


@dataclasses.dataclass
class NanoTdfEnvelope(DataclassMixin):
    @dataclasses.dataclass
    class Payload(DataclassMixin):
        length: int = csfield(Int24ub)
        iv: int = csfield(Int24ub)
        ciphertext: bytes = csfield(
            Bytes(
                this.length
                - 3
                - this._.header.symmetric_and_payload_config.symmetric_cipher_mode.mac_length
            )
        )
        mac: bytes = csfield(
            Bytes(
                this._.header.symmetric_and_payload_config.symmetric_cipher_mode.mac_length
            )
        )
        def pretty(self) -> str:
            return "\n".join([
                enc_hex_w_comment(construct.Int24ub.build(self.length), "length"),
                enc_hex_w_comment(construct.Int24ub.build(self.iv), "iv"),
                enc_hex_w_comment(self.ciphertext, "ciphertext"),
                enc_hex_w_comment(self.mac, "mac"),
            ])

    @dataclasses.dataclass
    class Signature(DataclassMixin):
        key: bytes = csfield(
            Bytes(
                this._._.symmetric_and_payload_config.signature_ecc_mode.public_key_length
            )
        )
        value: bytes = csfield(
            Bytes(
                this._.header.symmetric_and_payload_config.signature_ecc_mode.signature_length
            )
        )
        def pretty(self) -> str:
            return "\n".join([
                enc_hex_w_comment(self.key, "bytes"),
                enc_hex_w_comment(self.value, "value"),
            ])

    header: Header = csfield(DataclassStruct(Header))
    payload: str = csfield(DataclassStruct(Payload))
    signature: str | None = csfield(
        If(
            this.header.symmetric_and_payload_config.has_signature,
            DataclassStruct(Signature),
        )
    )

    def pretty(self) -> str:
        segments = [
           "## header",
           self.header.pretty(),
           "\n## payload",
           self.payload.pretty(),
        ]
        if self.signature:
            segments += ["\n## signature", self.signature.pretty()]
        return "\n".join(segments)

def parse(raw: bytes) -> NanoTdfEnvelope:
    ntdf_format = DataclassStruct(NanoTdfEnvelope)
    return ntdf_format.parse(raw)
