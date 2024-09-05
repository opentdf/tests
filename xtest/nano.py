import dataclasses
import logging

import construct as cs
import construct_typed as ct

logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)


def enc_hex(B: bytes) -> str:
    """Pretty print bytes as a block of hex bytes, suitable for formatting."""
    strides = [B[i * 20 : (i + 1) * 20] for i in range((len(B) + 19) // 20)]

    def to_s(n: int) -> str:
        return hex(n)[2:].zfill(2)

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
        [
            dec_hex(line.partition("#")[0].rstrip())
            for line in hexes_w_comments.split("\n")
        ]
    )


class UrlProtocol(ct.EnumBase):
    HTTP = 0
    HTTPS = 1


class EccMode(ct.EnumBase):
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
        raise ValueError("invalid ECC mode")

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


class SymmetricCipherMode(ct.EnumBase):
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
        raise ValueError("invalid EC cipher mode")

    def __getitem__(self, key):
        return getattr(self, key)


class PolicyType(ct.EnumBase):
    REMOTE = 0
    EMBEDDED = 1
    ENCRYPTED = 2
    ENCRYPTED_PKA = 3


@dataclasses.dataclass
class MagicAndVersion(ct.DataclassMixin):
    magic: int = ct.csfield(cs.Const(0b0100_1100_0011_0001_01, cs.BitsInteger(18)))
    version: int = ct.csfield(cs.BitsInteger(6))

    def __bytes__(self) -> bytes:
        return magic_and_version_format.build(self)


magic_and_version_format = ct.DataclassBitStruct(MagicAndVersion)


class KeyIdType(ct.EnumBase):
    UNSPECIFIED = 0
    ID_2 = 1
    ID_8 = 2
    ID_32 = 3

    @property
    def size(self) -> int:
        if self == KeyIdType.ID_2:
            return 2
        if self == KeyIdType.ID_8:
            return 8
        if self == KeyIdType.ID_32:
            return 32
        return 0

    def __getitem__(self, key):
        return getattr(self, key)


@dataclasses.dataclass
class ResourceLocator(ct.DataclassMixin):
    @dataclasses.dataclass
    class ProtocolAndKeyIdType(ct.DataclassMixin):
        kid_type: KeyIdType = ct.csfield(ct.TEnum(cs.BitsInteger(4), KeyIdType))
        protocol: UrlProtocol = ct.csfield(ct.TEnum(cs.BitsInteger(4), UrlProtocol))

    info: ProtocolAndKeyIdType = ct.csfield(ct.DataclassBitStruct(ProtocolAndKeyIdType))
    body: str = ct.csfield(cs.PascalString(cs.Int8ub, "utf8"))
    kid: bytes | None = ct.csfield(
        cs.If(
            cs.this.info.kid_type != KeyIdType.UNSPECIFIED,
            cs.Bytes(cs.this.info.kid_type.size),
        )
    )

    def __bytes__(self) -> bytes:
        return resource_locator_format.build(self)


def locator(url: str, kid: bytes | None = None) -> ResourceLocator:
    if url.startswith("https://"):
        protocol = UrlProtocol.HTTPS
        url = url[8:]
    elif url.startswith("http://"):
        protocol = UrlProtocol.HTTP
        url = url[7:]
    else:
        raise ValueError(f"invalid kas url [{url}]")
    if not kid:
        return ResourceLocator(
            info=ResourceLocator.ProtocolAndKeyIdType(KeyIdType.UNSPECIFIED, protocol),
            body=url,
            kid=None,
        )
    padding = 0
    if len(kid) <= 2:
        key_type = KeyIdType.ID_2
        padding = 2 - len(kid)
    elif len(kid) <= 8:
        key_type = KeyIdType.ID_8
        padding = 8 - len(kid)
    elif len(kid) <= 32:
        key_type = KeyIdType.ID_32
        padding = 32 - len(kid)
    else:
        raise ValueError(f"invalid kas kid [{kid}]")
    kid = b"\0" * padding + kid
    return ResourceLocator(
        info=ResourceLocator.ProtocolAndKeyIdType(key_type, protocol),
        body=url,
        kid=kid,
    )


resource_locator_format = ct.DataclassStruct(ResourceLocator)


@dataclasses.dataclass
class BindingMode(ct.DataclassMixin):
    use_ecdsa_binding: bool = ct.csfield(cs.Flag)
    unused: int = ct.csfield(cs.Const(0b0000, cs.BitsInteger(4)))
    ecc_params: EccMode = ct.csfield(ct.TEnum(cs.BitsInteger(3), EccMode))

    def __bytes__(self) -> bytes:
        return binding_mode_format.build(self)


binding_mode_format = ct.DataclassBitStruct(BindingMode)


@dataclasses.dataclass
class SymmetricAndPayloadConfig(ct.DataclassMixin):
    has_signature: bool = ct.csfield(cs.Flag)
    signature_ecc_mode: EccMode = ct.csfield(ct.TEnum(cs.BitsInteger(3), EccMode))
    symmetric_cipher_mode: SymmetricCipherMode = ct.csfield(
        ct.TEnum(cs.BitsInteger(4), SymmetricCipherMode)
    )

    def __bytes__(self) -> bytes:
        return symmetric_and_payload_config_format.build(self)


symmetric_and_payload_config_format = ct.DataclassBitStruct(SymmetricAndPayloadConfig)


# ??? taken from go parser but cs.this seems wrong
@dataclasses.dataclass
class EcdsaBinding(ct.DataclassMixin):
    length_r: int = ct.csfield(cs.Int8ub)
    r: bytes = ct.csfield(cs.Bytes(cs.this.length_r))
    length_s: int = ct.csfield(cs.Int8ub)
    s: bytes = ct.csfield(cs.Bytes(cs.this.length_s))

    def __bytes__(self) -> bytes:
        return ecdsa_binding_format.build(self)


ecdsa_binding_format = ct.DataclassStruct(EcdsaBinding)


@dataclasses.dataclass
class Policy(ct.DataclassMixin):
    policy_type: PolicyType = ct.csfield(ct.TEnum(cs.Int8ub, PolicyType))

    embedded: str | None = ct.csfield(
        cs.If(
            cs.this.policy_type == PolicyType.EMBEDDED,
            cs.PascalString(cs.Int16ub, "utf8"),
        )
    )

    encrypted_length: int | None = ct.csfield(
        cs.If(
            cs.this.policy_type == PolicyType.ENCRYPTED
            or cs.this.policy_type == PolicyType.ENCRYPTED_PKA,
            cs.Int16ub,
        )
    )
    encrypted: bytes | None = ct.csfield(
        cs.If(
            cs.this.policy_type == PolicyType.ENCRYPTED
            or cs.this.policy_type == PolicyType.ENCRYPTED_PKA,
            cs.Bytes(cs.this.encrypted_length),
        )
    )

    remote: ResourceLocator | None = ct.csfield(
        cs.If(
            cs.this.policy_type == PolicyType.REMOTE,
            ct.DataclassStruct(ResourceLocator),
        )
    )

    def __bytes__(self) -> bytes:
        return policy_format.build(self)


policy_format = ct.DataclassStruct(Policy)


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
class Header(ct.DataclassMixin):
    version: MagicAndVersion = ct.csfield(ct.DataclassBitStruct(MagicAndVersion))
    kas: ResourceLocator = ct.csfield(ct.DataclassStruct(ResourceLocator))
    binding_mode: BindingMode = ct.csfield(ct.DataclassBitStruct(BindingMode))
    symmetric_and_payload_config: SymmetricAndPayloadConfig = ct.csfield(
        ct.DataclassBitStruct(SymmetricAndPayloadConfig)
    )
    policy: Policy = ct.csfield(ct.DataclassStruct(Policy))

    ecdsa_binding: EcdsaBinding | None = ct.csfield(
        cs.If(cs.this.binding_mode.use_ecdsa_binding, ct.DataclassStruct(EcdsaBinding))
    )
    gmac_binding: bytes | None = ct.csfield(
        cs.IfThenElse(cs.this.binding_mode.use_ecdsa_binding, cs.Pass, cs.Bytes(8))
    )

    ephemeral_key: bytes = ct.csfield(
        cs.Bytes(
            cs.this.symmetric_and_payload_config.signature_ecc_mode.public_key_length
        )
    )

    def pretty(self) -> str:
        keys = [
            "version",
            "kas",
            "binding_mode",
            "symmetric_and_payload_config",
            "policy",
        ]
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


header_format = ct.DataclassStruct(Header)


@dataclasses.dataclass
class NanoTdfEnvelope(ct.DataclassMixin):
    @dataclasses.dataclass
    class Payload(ct.DataclassMixin):
        length: int = ct.csfield(cs.Int24ub)
        iv: int = ct.csfield(cs.Int24ub)
        ciphertext: bytes = ct.csfield(
            cs.Bytes(
                cs.this.length
                - 3
                - cs.this._.header.symmetric_and_payload_config.symmetric_cipher_mode.mac_length
            )
        )
        mac: bytes = ct.csfield(
            cs.Bytes(
                cs.this._.header.symmetric_and_payload_config.symmetric_cipher_mode.mac_length
            )
        )

        def pretty(self) -> str:
            return "\n".join(
                [
                    enc_hex_w_comment(cs.Int24ub.build(self.length), "length"),
                    enc_hex_w_comment(cs.Int24ub.build(self.iv), "iv"),
                    enc_hex_w_comment(self.ciphertext, "ciphertext"),
                    enc_hex_w_comment(self.mac, "mac"),
                ]
            )

    @dataclasses.dataclass
    class Signature(ct.DataclassMixin):
        key: bytes = ct.csfield(
            cs.Bytes(
                cs.this._._.symmetric_and_payload_config.signature_ecc_mode.public_key_length
            )
        )
        value: bytes = ct.csfield(
            cs.Bytes(
                cs.this._.header.symmetric_and_payload_config.signature_ecc_mode.signature_length
            )
        )

        def pretty(self) -> str:
            return "\n".join(
                [
                    enc_hex_w_comment(self.key, "bytes"),
                    enc_hex_w_comment(self.value, "value"),
                ]
            )

    header: Header = ct.csfield(ct.DataclassStruct(Header))
    payload: Payload = ct.csfield(ct.DataclassStruct(Payload))
    signature: Signature | None = ct.csfield(
        cs.If(
            cs.this.header.symmetric_and_payload_config.has_signature,
            ct.DataclassStruct(Signature),
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
    ntdf_format = ct.DataclassStruct(NanoTdfEnvelope)
    return ntdf_format.parse(raw)
