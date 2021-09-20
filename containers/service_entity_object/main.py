import datetime
import os
from enum import Enum
from typing import Optional

import databases as databases
import jwt
import sqlalchemy
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

app = FastAPI()

# application
ENTITY_ID_HEADER = os.getenv("ENTITY_ID_HEADER")

# database
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DATABASE = os.getenv("POSTGRES_DATABASE")
POSTGRES_SCHEMA = os.getenv("POSTGRES_SCHEMA")

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}/{POSTGRES_DATABASE}"
database = databases.Database(DATABASE_URL)

metadata = sqlalchemy.MetaData(schema=POSTGRES_SCHEMA)

table_entity_attribute = sqlalchemy.Table(
    "entity_attribute",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("entity_id", sqlalchemy.VARCHAR),
    sqlalchemy.Column("namespace", sqlalchemy.VARCHAR),
    sqlalchemy.Column("name", sqlalchemy.VARCHAR),
    sqlalchemy.Column("value", sqlalchemy.VARCHAR),
)

engine = sqlalchemy.create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)


@app.middleware("http")
async def add_response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


class EntityObjectRequest(BaseModel):
    algorithm: Optional[str] = None
    publicKey: str
    signerPublicKey: Optional[str] = ""
    userId: str

    class Config:
        schema_extra = {
            "example": {
                "algorithm": "ec:secp256r1",
                "publicKey": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA2Q9axUqaxEfhOO2+0Xw+\nswa5Rb2RV0xeTX3GC9DeORv9Ip49oNy+RXvaMsdNKspPWYZZEswrz2+ftwcQOSU+\nefRCbGIwbSl8QBfKV9nGLlVmpDydcAIajc7YvWjQnDTEpHcJdo9y7/oogG7YcEmq\nS3NtVJXCmbc4DyrZpc2BmZD4y9417fSiNjTTYY3Fc19lQz07hxDQLgMT21N4N0Fz\nmD6EkiEpG5sdpDT/NIuGjFnJEPfqIs6TnPaX2y1OZ2/JzC+mldJFZuEqJZ/6qq/e\nYlp04nWrSnXhPpTuxNZ5J0GcPbpcFgdT8173qmm5m5jAjiFCr735lH7USl15H2fW\nTwIDAQAB\n-----END PUBLIC KEY-----\n",
                "userId": "Charlie_1234",
            }
        }


class EntityObject(BaseModel):
    publicKey: str
    signerPublicKey: Optional[str] = ""
    userId: str
    cert: Optional[str] = None
    exp: Optional[float]
    aliases: Optional[list] = []
    attributes: list

    class Config:
        schema_extra = {
            "example": {
                "aliases": ["string"],
                "attributes": [
                    {
                        "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
                    }
                ],
                "cert": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
                "exp": 1611387008.338341,
                "publicKey": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA2Q9axUqaxEfhOO2+0Xw+\nswa5Rb2RV0xeTX3GC9DeORv9Ip49oNy+RXvaMsdNKspPWYZZEswrz2+ftwcQOSU+\nefRCbGIwbSl8QBfKV9nGLlVmpDydcAIajc7YvWjQnDTEpHcJdo9y7/oogG7YcEmq\nS3NtVJXCmbc4DyrZpc2BmZD4y9417fSiNjTTYY3Fc19lQz07hxDQLgMT21N4N0Fz\nmD6EkiEpG5sdpDT/NIuGjFnJEPfqIs6TnPaX2y1OZ2/JzC+mldJFZuEqJZ/6qq/e\nYlp04nWrSnXhPpTuxNZ5J0GcPbpcFgdT8173qmm5m5jAjiFCr735lH7USl15H2fW\nTwIDAQAB\n-----END PUBLIC KEY-----\n",
                "schemaVersion": "1.1.0",
                "userId": "Charlie_1234",
            }
        }


# crypto
private_key = str.encode(os.getenv("EAS_PRIVATE_KEY", ""))
kas_rsa_certificate_pem: str = ""
kas_ec_certificate_pem: str = ""


@app.on_event("startup")
async def startup():
    global private_key
    private_key = str.encode(os.getenv("EAS_PRIVATE_KEY", ""))
    kas_rsa_certificate = x509.load_pem_x509_certificate(
        str.encode(os.getenv("KAS_CERTIFICATE", ""))
    )
    global kas_rsa_certificate_pem
    kas_rsa_certificate_pem = kas_rsa_certificate.public_bytes(
        encoding=serialization.Encoding.PEM,
    ).decode("utf-8")
    kas_ec_certificate = x509.load_pem_x509_certificate(
        str.encode(os.getenv("KAS_EC_SECP256R1_CERTIFICATE", ""))
    )
    global kas_ec_certificate_pem
    kas_ec_certificate_pem = kas_ec_certificate.public_bytes(
        encoding=serialization.Encoding.PEM,
    ).decode("utf-8")
    await database.connect()


@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


@app.get("/")
async def read_semver():
    return {"Hello": "World"}


class ProbeType(str, Enum):
    liveness = "liveness"
    readiness = "readiness"


@app.get("/healthz", status_code=204)
async def read_liveness(probe: ProbeType = ProbeType.liveness):
    if probe == ProbeType.readiness:
        await database.execute("SELECT 1")


@app.post("/v1/entity_object", response_model=EntityObject)
async def create_entity_object(eo_request: EntityObjectRequest, request: Request):
    # validate
    if ENTITY_ID_HEADER and ENTITY_ID_HEADER not in request.headers:
        raise HTTPException(
            status_code=403, detail=f"missing entity header: {ENTITY_ID_HEADER}"
        )
    if ENTITY_ID_HEADER and request.headers[ENTITY_ID_HEADER] != eo_request.userId:
        raise HTTPException(
            status_code=403,
            detail=f"entity header: {request.headers[ENTITY_ID_HEADER]} not equal userId: {eo_request.userId}",
        )
    try:
        if eo_request.publicKey:
            serialization.load_pem_public_key(str.encode(eo_request.publicKey))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"publicKey: {str(e)}") from e
    try:
        if eo_request.signerPublicKey:
            serialization.load_pem_public_key(str.encode(eo_request.signerPublicKey))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"signerPublicKey: {str(e)}") from e
    attributes = []
    # select
    query = table_entity_attribute.select().where(
        table_entity_attribute.c.entity_id == eo_request.userId
    )
    result = await database.fetch_all(query)
    for row in result:
        attributes.append(
            f"{row.get(table_entity_attribute.c.namespace)}/attr/{row.get(table_entity_attribute.c.name)}/value/{row.get(table_entity_attribute.c.value)}"
        )
    # performance hotspot
    # - cache jwt if no expiration, no expire = 99 years
    # - async await jwt operations
    # default attribute
    if eo_request.algorithm == "ec:secp521r1":
        kas_certificate_pem = kas_ec_certificate_pem
    else:
        kas_certificate_pem = kas_rsa_certificate_pem
    jwt_attributes = [
        to_jwt(
            f'{os.getenv("KAS_DEFAULT_URL")}/attr/default/value/default',
            kas_certificate_pem,
            True,
        )
    ]
    for attribute in attributes:
        jwt_attributes.append(to_jwt(attribute, kas_certificate_pem))
    eo = EntityObject(
        userId=eo_request.userId,
        exp=exp_env_to_time(),
        publicKey=eo_request.publicKey,
        signerPublicKey=eo_request.signerPublicKey,
        attributes=jwt_attributes,
    )
    eo.cert = jwt.encode(eo.dict(), private_key, "RS256")
    return eo


def to_jwt(attribute: str, kas_certificate_pem: str, default: bool = False):
    """Export a jwt form."""
    raw = {
        "attribute": attribute,
        "isDefault": default,
        "displayName": "",
        "pubKey": kas_certificate_pem,
        "kasUrl": os.getenv("KAS_DEFAULT_URL"),
        "exp": exp_env_to_time(),
    }
    return {"jwt": jwt.encode(raw, private_key, "RS256")}


def exp_env_to_time():
    value = os.getenv("EAS_ENTITY_EXPIRATION")
    if value:
        env_value = {"exp_days": int(value)}
        exptime = {
            "exp_days": "days",
            "exp_hours": "hours",
            "exp_mins": "minutes",
            "exp_sec": "seconds",
        }
        key, value = next(iter(env_value.items()))
        if key not in exptime:
            raise Error(
                "Undefined value in EAS_ENTITY_EXPIRATION variable. Use exp_days, exp_hrs, exp_min or exp_sec"
            )
        if value <= 0:
            raise Error(
                "Value in EAS_ENTITY_EXPIRATION variable is negative or equal 0. Use positive number"
            )
        kwargs = {exptime[key]: value}
        now = datetime.datetime.now()
        delta = datetime.timedelta(**kwargs)
        return (now + delta).timestamp()


class Error(Exception):
    """The base class for custom expressions, including standard problem details message used for errors.
    From https://tools.ietf.org/html/draft-ietf-appsawg-http-problem-00.
    Not all fields are implemented."""

    def __init__(self, message: str = None, title: str = "Problem", status: int = 500):
        # Human-readable summary of problem
        self.title = title
        # Detail: An human readable explanation specific to this occurrence of the problem.
        self.message = message
        # http status code
        self.status = status

    def to_raw(self):
        return {"title": self.title, "detail": self.message, "status": self.status}
