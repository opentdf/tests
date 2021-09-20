"""Test the authorization process between client and KAS."""

import pytest

from tdf3_kas_core.authorized import pack_rs256_jwt
from tdf3_kas_core.errors import AuthorizationError
from tdf3_kas_core.errors import UnauthorizedError
from tdf3_kas_core.errors import JWTError
from tdf3_kas_core.util import get_public_key_from_disk
from tdf3_kas_core.util import get_private_key_from_disk

from . import authorized

entity_private_key = get_private_key_from_disk("test")
entity_public_key = get_public_key_from_disk("test")
other_public_key = get_public_key_from_disk("test_alt")

slightly_borked_jwt = """"eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUI
iwia2lkIiA6ICJXcGNJNjdBdjhtb2ItY2Vqa3NtWkJ5R2otcllmUURDMTBLa1V
4ZHhnTTlRIn0.eyJleHAiOjE2MjMzNjI4ODYsImlhdCI6MTYyMzM2MjU4Niwia
nRpIjoiYWE0Njg5NzYtODA2MC00M2NkLWFmNjYtMTc1NzE0NGFiMmY4IiwiaXN
zIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwL2F1dGgvcmVhbG1zL3RkZisImF1ZC
I6ImFjY291bnQiLCJzdWIiOiI4ZTZkZTAyMC0zNjE3LTQzNmUtYTQ5Ny1mZWRl
ZDRjNjRmMTAiLCJ0eXAiOiJCZWFyZXIiLCJhenAiOiJ0ZGYtY2xpZW50Iiwic2
Vzc2lvbl9zdGF0ZSI6IjYzZGU2YjM2LWEwNjYtNGVmZi1hYWNhLTM1OWQ2Zjlh
ZWZmNiIsImFjciI6IjEiLCJhbGxvd2VkLW9yaWdpbnMiOlsiaHR0cDovL2tleW
Nsb2FrLWh0dHAiXSwicmVhbG1fYWNjZXNzIjp7InJvbGVzIjpbImRlZmF1bHQt
cm9sZXMtdGRmIiwib2ZmbGluZV9hY2Nlc3MiLCJ1bWFfYXV0aG9yaXphdGlvbi
JdfSwicmVzb3VyY2VfYWNjZXNzIjp7ImFjY291bnQiOnsicm9sZXMiOlsibWFu
YWdlLWFjY291bnQiLCJtYW5hZ2UtYWNjb3VudC1saW5rcyIsInZpZXctcHJvZm
lsZSJdfX0sInNjb3BlIjoicHJvZmlsZSBlbWFpbCIsImVtYWlsX3ZlcmlmaWVk
IjpmYWxzZSwicHJlZmVycmVkX3VzZXJuYW1lIjoidXNlcjEifQ.HVyCjVtoTie
iuZBOc1A03WEjQCTh5Br01RHXTQbRl3YDC6zS3H1UwELHGELJhxlYPepF7cKH7
4-jn4G4PTjPCplFyQ0GWyG0oAadH-o4LfMfmV4w1dIKRn7JNfykC3aggv3eRT8
aNZ1an8VFX69Kl5wFeiu8i4FljjDm-X15OMWHois6kA0GSqmC5QIbZSRQwazpj
crf1b85SvbrZl6tBrOToFVTdWOoNwQCMLj28W_ZFLb9U2se8ADe3ViM71f-b96
TflXyM4Jk7qPhVcP8gVmHfdq6RNKi2MvY_jOqU384dUojHBfrUP5FJVXGUKDHV
D54ic3t2yZtcN8dqe26LA
"""


def test_authorized_pass():
    """Test authorized."""
    auth_token = pack_rs256_jwt({}, entity_private_key, exp_sec=60)
    assert authorized.authorized(entity_public_key, auth_token)


def test_authorized_fail():
    """Test authorized failure."""
    auth_token = pack_rs256_jwt({}, entity_private_key, exp_sec=60)
    with pytest.raises(AuthorizationError):
        authorized.authorized(other_public_key, auth_token)


def test_jwt_utilities_unsafe_decode_jwt_fails_on_malformed_jwt():
    with pytest.raises(UnauthorizedError):
        assert authorized.unsafe_decode_jwt(slightly_borked_jwt)


def test_jwt_utilities_rs256test_happy():
    """Test creation/validation of asymmetric JWTs with RSA key pairs."""
    expected = {"foo": "bar"}
    private = get_private_key_from_disk("test")
    public = get_public_key_from_disk("test")
    jwt = authorized.pack_rs256_jwt(expected, private)
    actual = authorized.unpack_rs256_jwt(jwt, public)
    assert actual == expected


def test_jwt_utilities_rs256_pack_sad():
    """Test validatation attempt with bogus public key."""
    expected = {"foo": "bar"}
    bogus = "bogus"
    with pytest.raises(Exception):
        authorized.pack_rs256_jwt(expected, bogus)


def test_jwt_utilities_rs256_unpack_sad():
    """Test validatation attempt with bogus public key."""
    expected = {"foo": "bar"}
    private = get_private_key_from_disk("test")
    bogus = get_public_key_from_disk("test_alt")
    jwt = authorized.pack_rs256_jwt(expected, private)
    with pytest.raises(JWTError):
        authorized.unpack_rs256_jwt(jwt, bogus)


def test_jwt_utilities_rs256_unpack_expiration_hrs():
    """Test validatation attempt with bogus public key."""
    expected = {"foo": "bar"}
    private = get_private_key_from_disk("test")
    public = get_public_key_from_disk("test")
    jwt = authorized.pack_rs256_jwt(expected, private, exp_hrs=-1)
    with pytest.raises(JWTError):
        authorized.unpack_rs256_jwt(jwt, public)


def test_jwt_utilities_rs256_unpack_expiration_sec():
    """Test validatation attempt with bogus public key."""
    expected = {"foo": "bar"}
    private = get_private_key_from_disk("test")
    public = get_public_key_from_disk("test")
    jwt = authorized.pack_rs256_jwt(expected, private, exp_sec=-1)
    with pytest.raises(JWTError):
        authorized.unpack_rs256_jwt(jwt, public)
