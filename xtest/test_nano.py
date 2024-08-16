import base64
import dataclasses

import construct
import construct_typed

import nano

from nano import dec_hex, enc_hex


def test_magic_version():
    mv0 = nano.MagicAndVersion(version=12)

    assert dec_hex("4c 31 4c") == bytes(mv0)
    assert b"L1L" == bytes(mv0)
    assert base64.b64encode(bytes(mv0)).startswith(b"TDF")

    # If we increment the version, the b64 variant increases as expected
    mv1 = nano.MagicAndVersion(version=13)
    assert b"L1M" == bytes(mv1)
    assert base64.b64encode(bytes(mv1)).startswith(b"TDF")


def test_resource_locator():
    rl0 = nano.ResourceLocator(nano.UrlProtocol.HTTPS, "localhost:8080/kas")

    expected_bits = "01 12 6c 6f 63 61 6c 68 6f 73 74 3a 38 30 38 30 2f 6b 61 73"
    assert (
        "localhost:8080/kas"
        == nano.resource_locator_format.parse(dec_hex(expected_bits)).body
    )

    assert expected_bits == enc_hex(nano.resource_locator_format.build(rl0))


def test_binding_mode():
    bm0 = nano.BindingMode(
        use_ecdsa_binding=True,
        ecc_params=nano.EccMode.secp256r1,
    )
    assert dec_hex("80") == nano.binding_mode_format.build(bm0)
    assert b"\x80" == bytes(nano.binding_mode_format.build(bm0))
    assert nano.binding_mode_format.parse(dec_hex("80")).use_ecdsa_binding

    assert not nano.binding_mode_format.parse(dec_hex("00")).use_ecdsa_binding


def test_sym_and_payload_cfg():
    sp0 = nano.SymmetricAndPayloadConfig(
        has_signature=False,
        signature_ecc_mode=nano.EccMode.secp256r1,
        symmetric_cipher_mode=nano.SymmetricCipherMode.AES_256_GCM_96,
    )
    sapc = nano.symmetric_and_payload_config_format
    assert dec_hex("01") == sapc.build(sp0)
    assert b"\1" == bytes(sapc.build(sp0))
    assert (
        nano.SymmetricCipherMode.AES_256_GCM_96
        == sapc.parse(b"\1").symmetric_cipher_mode
    )
    assert not sapc.parse(b"\1").has_signature
    assert sapc.parse(dec_hex("80")).has_signature

    assert 33 == nano.EccMode.secp256r1.public_key_length



def test_nested_stuff():
    @dataclasses.dataclass
    class Outer(construct_typed.DataclassMixin):
        @dataclasses.dataclass
        class A(construct_typed.DataclassMixin):
            f1: int = construct_typed.csfield(construct.Int8ub)
        @dataclasses.dataclass
        class B(construct_typed.DataclassMixin):
            f2: int = construct_typed.csfield(construct.Int8ub)
        @dataclasses.dataclass
        class C(construct_typed.DataclassMixin):
            f3: int = construct_typed.csfield(construct.PascalString(construct.Int8ub, "utf8"))

        o1: int = construct_typed.csfield(construct.Byte)
        a: A = construct_typed.csfield(construct_typed.DataclassStruct(A))
        b: B = construct_typed.csfield(construct_typed.DataclassStruct(B))
        c: C = construct_typed.csfield(construct_typed.DataclassStruct(C))

    f = construct_typed.DataclassStruct(Outer)
    oval = Outer(0, Outer.A(1), Outer.B(2), Outer.C("abc"))
    assert f.build(oval) == b'\x00\x01\x02\x03abc'


def test_sibling_stuff():
    @dataclasses.dataclass
    class A(construct_typed.DataclassMixin):
        f1: int = construct_typed.csfield(construct.Int8ub)
    @dataclasses.dataclass
    class B(construct_typed.DataclassMixin):
        f2: int = construct_typed.csfield(construct.Int8ub)
    @dataclasses.dataclass
    class C(construct_typed.DataclassMixin):
        f3: int = construct_typed.csfield(construct.PascalString(construct.Int8ub, "utf8"))

    @dataclasses.dataclass
    class Outer(construct_typed.DataclassMixin):
        o1: int = construct_typed.csfield(construct.Byte)
        a: A = construct_typed.csfield(construct_typed.DataclassStruct(A))
        b: B = construct_typed.csfield(construct_typed.DataclassStruct(B))
        c: C = construct_typed.csfield(construct_typed.DataclassStruct(C))

    f = construct_typed.DataclassStruct(Outer)
    oval = Outer(0, A(1), B(2), C("abc"))
    assert f.build(oval) == b'\x00\x01\x02\x03abc'


def test_sibling_stuff_with_enums():
    class AnEnum(construct_typed.EnumBase):
        U = 0
        A = 1
        B = 2
        C = 3

    @dataclasses.dataclass
    class A(construct_typed.DataclassMixin):
        f1: int = construct_typed.csfield(construct.Int8ub)
    @dataclasses.dataclass
    class B(construct_typed.DataclassMixin):
        f2: int = construct_typed.csfield(construct.Int8ub)
    @dataclasses.dataclass
    class C(construct_typed.DataclassMixin):
        f3a: AnEnum = construct_typed.csfield(construct_typed.TEnum(construct.Int8ub, AnEnum))
        f3b: int = construct_typed.csfield(construct.PascalString(construct.Int8ub, "utf8"))

    @dataclasses.dataclass
    class Outer(construct_typed.DataclassMixin):
        o1: int = construct_typed.csfield(construct.Byte)
        a: A = construct_typed.csfield(construct_typed.DataclassStruct(A))
        b: B = construct_typed.csfield(construct_typed.DataclassStruct(B))
        c: C = construct_typed.csfield(construct_typed.DataclassStruct(C))

    f = construct_typed.DataclassStruct(Outer)
    oval = Outer(0, A(1), B(2), C(AnEnum.B, "abc"))
    assert f.build(oval) == b'\x00\x01\x02\x02\x03abc'


def test_sibling_stuff_with_bits():
    class AnEnum(construct_typed.EnumBase):
        U = 0
        A = 1
        B = 2
        C = 3

    @dataclasses.dataclass
    class A(construct_typed.DataclassMixin):
        f1: int = construct_typed.csfield(construct.Int8ub)
    @dataclasses.dataclass
    class B(construct_typed.DataclassMixin):
        flag: int = construct_typed.csfield(construct.BitsInteger(2))
        version: int = construct_typed.csfield(construct.BitsInteger(6))
    @dataclasses.dataclass
    class C(construct_typed.DataclassMixin):
        f3a: AnEnum = construct_typed.csfield(construct_typed.TEnum(construct.Int8ub, AnEnum))
        f3b: int = construct_typed.csfield(construct.PascalString(construct.Int8ub, "utf8"))

    @dataclasses.dataclass
    class Outer(construct_typed.DataclassMixin):
        o1: int = construct_typed.csfield(construct.Byte)
        a: A = construct_typed.csfield(construct_typed.DataclassStruct(A))
        b: B = construct_typed.csfield(construct_typed.DataclassBitStruct(B))
        c: C = construct_typed.csfield(construct_typed.DataclassStruct(C))

    f = construct_typed.DataclassStruct(Outer)
    oval = Outer(0, A(1), B(0, 2), C(AnEnum.B, "abc"))
    assert f.build(oval) == b'\x00\x01\x02\x02\x03abc'

def test_policy():
    p1 = nano.embedded_policy("{}")
    assert "01 00 02 7b 7d" == enc_hex(nano.policy_format.build(p1))
    assert b"\x01\x00\x02{}" == bytes(nano.policy_format.build(p1))

    p2 = nano.encrypted_policy(b"\0\1\2\3")
    assert "02 00 04 00 01 02 03" == enc_hex(nano.policy_format.build(p2))

    # TK PKA doesn't work since the length is defined in the header
    # and i don't know how to hint to construct-typed what it should be
    # p3 = nano.encrypted_policy(
    #     b"\0\1\2\3",
    #     nano.PolicyKeyAccess(
    #         nano.ResourceLocator(nano.UrlProtocol.HTTP, "a.b"),
    #         b"a fake key "*3,
    #     ),
    # )
    # assert "03 00 04 00 01 02 03 " == enc_hex(policy.build(p3))

    b2 = "02 00 68 ef 70 7b 5f 20 b9 0b f5 96 c3 d7 42  85 17 6c d8 98 ad 47 c4 9a 81 5f 67 c4 0f ff 16 bb f0 f4 cd 31 a5 f6 86 59 3d f1 53 39 3c 3e 16 d8 d2 3b 37 50 86 6c fd 2b ce c7 10 89 66 74 22 f0 3f 16 7a ed 37 93 03 30 cc 05 21 d2 9e 5d c3 34 c5 51 60 e6 bf 16 df 92 d0 8d b0 f0 57 6f 7c 37 b9 84 44 c7 64 99 6a d3 6e aa 04"
    assert (
        nano.policy_format.parse(dec_hex(b2)).policy_type == nano.PolicyType.ENCRYPTED
    )


def test_header():
    h0 = nano.Header(
        version=nano.MagicAndVersion(version=12),
        kas=nano.ResourceLocator(
            protocol_type=nano.UrlProtocol.HTTP,
            body="nano.org",
        ),
        binding_mode=nano.BindingMode(
            use_ecdsa_binding=False,
            ecc_params=nano.EccMode.secp256r1,
        ),
        symmetric_and_payload_config=nano.SymmetricAndPayloadConfig(
            has_signature=False,
            signature_ecc_mode=nano.EccMode.secp256r1,
            symmetric_cipher_mode=nano.SymmetricCipherMode.AES_256_GCM_96,
        ),
        policy=nano.embedded_policy("{}"),
        gmac_binding=b"ABCDABCD",
        ecdsa_binding=None,
        ephemeral_key=(b"1234567890" * 4)[:33],
    )
    pretty = """4c 31 4c # version
00 08 6e 61 6e 6f 2e 6f 72 67 # kas
00 # binding_mode
01 # symmetric_and_payload_config
01 00 02 7b 7d # policy
41 42 43 44 41 42 43 44 # gmac_binding

# ephemeral_key
31 32 33 34 35 36 37 38 39 30 31 32 33 34 35 36 37 38 39 30
31 32 33 34 35 36 37 38 39 30 31 32 33"""
    assert pretty == h0.pretty()
    h1raw = nano.dec_hex_w_comments(pretty)
    assert h1raw == nano.header_format.build(h0)
    h1 = nano.header_format.parse(h1raw)
    assert h0 == h1


whole_go = """## header
4c 31 4c # version
00 12 6c 6f 63 61 6c 68 6f 73 74 3a 38 30 38 30 2f 6b 61 73 # kas
00 # binding_mode
01 # symmetric_and_payload_config

# policy
02 00 68 ef 70 7b 5f 20 b9 0b f5 96 c3 d7 42 85 17 6c d8 98
ad 47 c4 9a 81 5f 67 c4 0f ff 16 bb f0 f4 cd 31 a5 f6 86 59
3d f1 53 39 3c 3e 16 d8 d2 3b 37 50 86 6c fd 2b ce c7 10 89
66 74 22 f0 3f 16 7a ed 37 93 03 30 cc 05 21 d2 9e 5d c3 34
c5 51 60 e6 bf 16 df 92 d0 8d b0 f0 57 6f 7c 37 b9 84 44 c7
64 99 6a d3 6e aa 04
f3 18 e9 0b d0 dc 05 38 # gmac_binding

# ephemeral_key
03 66 95 d9 3b 84 ee c5 65 c1 13 1c 94 c6 00 8b cb 6a f5 90
d5 0d 90 c5 f4 e5 96 56 b2 d9 4a 9b 51

## payload
00 00 8f # length
54 2b 53 # iv

# ciphertext
ce 35 1d 0a d9 7a 81 b5 da 93 39 d5 a2 42 22 a3 64 97 2e 33
41 84 12 26 81 f5 10 c9 f4 94 b8 55 52 24 eb af 89 c3 24 7e
32 cf d5 da a2 cb 98 67 71 c3 a5 f6 a8 e3 4e 64 23 2e 40 ee
2e d9 a4 97 87 83 d4 e7 11 fe db f4 42 c1 71 3b 5a 07 01 76
b2 f8 48 23 2d b3 53 61 98 39 13 7b 45 cd 55 76 be 71 3a 88
f3 ce ec c2 68 7d fd 38 4d 49 ef 57 9a c7 45 81 e4 6f ab 4b
50 a2 43 08 71 78 43 a2
66 8e 2b fd 64 c3 ed 09 1f a6 e8 a2 # mac"""


def test_whole_go():
    h0 = nano.header_format.parse(nano.dec_hex_w_comments(whole_go))
    assert h0.pretty() in whole_go

    e0 = nano.parse(nano.dec_hex_w_comments(whole_go))
    assert e0.pretty() == whole_go


whole_js = """## header
4c 31 4c # version
00 12 6c 6f 63 61 6c 68 6f 73 74 3a 38 30 38 30 2f 6b 61 73 # kas
00 # binding_mode
01 # symmetric_and_payload_config

# policy
02 00 64 23 66 5c df 40 f3 56 46 3c da c8 c0 01 09 94 83 90
23 e6 0c 55 ce 8b b4 ee d8 c0 97 89 86 15 3f a7 95 6a bb d1
d0 77 85 cc 88 2a 79 c7 fe 47 2d 0a fb 81 6f db 83 f2 54 d9
d9 50 8e e4 5f 70 7f b2 1d 2e 31 aa 30 55 a7 3e 14 4b 11 33
8b 0f 0c 71 fa e9 d1 6d e2 83 bf fc 67 fe e4 23 a2 67 d6 d7
5a 00 44
ce 05 fc d0 14 d9 31 47 # gmac_binding

# ephemeral_key
02 29 44 e4 e5 aa 02 77 29 9c 2d 80 36 fc 0c 8e 8b 92 e1 cc
c6 3e 34 4e 66 0e 58 8c 13 4b 03 19 8f

## payload
00 00 8f # length
00 00 01 # iv

# ciphertext
63 39 fc 77 72 44 e9 50 84 9d d1 91 9f d9 c9 7b 58 ee 9c 83
c0 c4 c2 5b 4a f4 4a b3 e7 ae 2d c2 55 84 c8 26 cc 3d 16 e7
53 48 2b 5b 45 7f be 8e b2 90 78 b8 23 4d 0c 8f 2a 87 d3 70
63 6f 56 29 96 e8 4d d1 8c 56 60 6e 4a 9b e0 2e fc 7b 4b b2
90 96 60 28 ef 75 4d 8c ca d5 19 73 96 19 61 ba a7 2a 73 99
ed 93 01 f9 f1 cb e5 fd b4 4e b6 b8 7c c2 d9 11 a7 54 bd 27
f4 0a bc 2f a7 76 46 83
21 28 13 90 09 89 cd b5 a4 26 3a 36 # mac"""


def test_whole_js():
    e0 = nano.parse(nano.dec_hex_w_comments(whole_js))
    assert e0.pretty() == whole_js
