import json
import logging
import os
import re
import sys
import requests
from enum import Enum
from http.client import NO_CONTENT, ACCEPTED, BAD_REQUEST
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from typing import Dict, List, Optional, Annotated

import databases as databases
import sqlalchemy
import uritools
from fastapi import (
    FastAPI,
    Body,
    Depends,
    HTTPException,
    Path,
    Request,
    Query,
    Security,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.security import OAuth2AuthorizationCodeBearer
from keycloak import KeycloakOpenID
from pydantic import AnyUrl, BaseSettings, Field, HttpUrl, Json, validator
from pydantic.main import BaseModel
from python_base import Pagination, get_query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, sessionmaker, declarative_base

logging.basicConfig(
    stream=sys.stdout, level=os.getenv("SERVER_LOG_LEVEL", "CRITICAL")
)
logger = logging.getLogger(__package__)

swagger_ui_init_oauth = {
    "usePkceWithAuthorizationCodeGrant": True,
    "clientId": os.getenv("OIDC_CLIENT_ID"),
    "realm": os.getenv("OIDC_REALM"),
    "appName": os.getenv("SERVER_PUBLIC_NAME"),
    "scopes": [os.getenv("OIDC_SCOPES")],
}


class Settings(BaseSettings):
    openapi_url: str = "/openapi.json"
    base_path: str = os.getenv("SERVER_ROOT_PATH", "")


settings = Settings()

app = FastAPI(
    debug=True,
    root_path=os.getenv("SERVER_ROOT_PATH", ""),
    servers=[{"url": settings.base_path}],
    swagger_ui_init_oauth=swagger_ui_init_oauth,
    openapi_url=settings.openapi_url,
)

# OpenAPI
tags_metadata = [
    {
        "name": "Entitlements",
        "description": "Operations to manage entitlements entitled to entities.",
    },
]


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="openTDF",
        version="1.0.0",
        license_info={"name": "MIT"},
        routes=app.routes,
        tags=tags_metadata,
    )
    openapi_schema["info"]["x-logo"] = {
        "url": "https://inxmad4bw31barrx17wec71c-wpengine.netdna-ssl.com/wp-content/uploads/2018/12/o_efa1e48d0db5ebc8-4.png"
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

app.add_middleware(
    CORSMiddleware,
    allow_origins=(os.environ.get("SERVER_CORS_ORIGINS", "").split(",")),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2AuthorizationCodeBearer(
    # format f"{keycloak_url}realms/{realm}/protocol/openid-connect/auth"
    authorizationUrl=os.getenv("OIDC_AUTHORIZATION_URL", ""),
    # format f"{keycloak_url}realms/{realm}/protocol/openid-connect/token"
    tokenUrl=os.getenv("OIDC_TOKEN_URL", ""),
)

keycloak_openid = KeycloakOpenID(
    # trailing / is required
    server_url=os.getenv("OIDC_SERVER_URL"),
    client_id=os.getenv("OIDC_CLIENT_ID"),
    realm_name=os.getenv("OIDC_REALM"),
    client_secret_key=os.getenv("OIDC_CLIENT_SECRET"),
    verify=True,
)

def get_retryable_request():
    retry_strategy = Retry(total=3, backoff_factor=1)

    adapter = HTTPAdapter(max_retries=retry_strategy)

    http = requests.Session()
    http.mount("https://", adapter)
    http.mount("http://", adapter)
    return http


# Given a realm ID, request that realm's public key from Keycloak's endpoint
#
# If anything fails, raise an exception
#
# TODO Consider replacing the endpoint here with the OIDC JWKS endpoint
# Keycloak exposes: `/auth/realms/{realm-name}/.well-known/openid-configuration`
# This is a low priority though since it doesn't save us from having to get the
# realmId first and so is a largely cosmetic difference
async def get_idp_public_key(realm_id):
    url = f"{os.getenv('OIDC_SERVER_URL')}/realms/{realm_id}"

    http = get_retryable_request()

    response = http.get(
        url, headers={"Content-Type": "application/json"}, timeout=5  # seconds
    )

    if not response.ok:
        logger.warning("No public key found for Keycloak realm %s", realm_id)
        raise RuntimeError(
            f"Failed to download Keycloak public key: [{response.text}]"
        )

    try:
        resp_json = response.json()
    except Exception as e:
        logger.warning(
            f"Could not parse response from Keycloak pubkey endpoint: {response}"
        )
        raise e

    keycloak_public_key = f"""-----BEGIN PUBLIC KEY-----
{resp_json['public_key']}
-----END PUBLIC KEY-----"""

    logger.debug("Keycloak public key for realm %s: [%s]", realm_id, keycloak_public_key)
    return keycloak_public_key

# Looks as `iss` header field of token - if this is a Keycloak-issued token,
# `iss` will have a value like 'https://<KEYCLOAK_SERVER>/auth/realms/<REALMID>
# so we can parse the URL parts to obtain the realm this token was issued from.
# Once we know that, we know where to get a pubkey to validate it.
#
# `urlparse` should be safe to use as a parser, and if the result is
# an invalid realm name, no validation key will be fetched, which simply will result
# in an access denied
def try_extract_realm(unverified_jwt):
    issuer_url = unverified_jwt["iss"]
    # Split the issuer URL once, from the right, on /,
    # then get the last element of the result - this will be
    # the realm name for a keycloak-issued token.
    return urlparse(issuer_url).path.rsplit("/", 1)[-1]

def has_aud(unverified_jwt, audience):
    aud = unverified_jwt["aud"]
    if not aud:
        logger.debug("No aud found in token [%s]", unverified_jwt)
        return False
    if isinstance(aud, str):
        aud = [aud]
    if audience not in aud:
        logger.debug("Audience mismatch [%s] ⊄ %s", audience, aud)
        return False
    return True

async def get_auth(token: str = Security(oauth2_scheme)) -> Json:
    try:
        unverified_decode = keycloak_openid.decode_token(
            token,
            key='',
            options={"verify_signature": False, "verify_aud": False, "exp": True},
        )
        if not has_aud(unverified_decode, "tdf-entitlement"):
            raise Exception("Invalid audience, should be tdf-entitlement")
        return keycloak_openid.decode_token(
            token,
            key=await get_idp_public_key(try_extract_realm(unverified_decode)),
            options={"verify_signature": True, "verify_aud": False, "exp": True},
        )
    except Exception as e:
        logger.warning("Unverifiable claims [%s]", token, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),  # "Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


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

engine = sqlalchemy.create_engine(DATABASE_URL)
dbase = sessionmaker(bind=engine)


def get_db() -> Session:
    session = dbase()
    try:
        yield session
    finally:
        session.close()


class EntityAttributeSchema(declarative_base()):
    __table__ = table_entity_attribute


@app.middleware("http")
async def add_response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.on_event("startup")
async def startup():
    await database.connect()


@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


@app.get("/", include_in_schema=False)
async def read_semver():
    return {"Hello": "entitlements"}


class ProbeType(str, Enum):
    liveness = "liveness"
    readiness = "readiness"


class AuthorityUrl(AnyUrl):
    max_length = 2000


@app.get("/healthz", status_code=NO_CONTENT, include_in_schema=False)
async def read_liveness(probe: ProbeType = ProbeType.liveness):
    if probe == ProbeType.readiness:
        await database.execute("SELECT 1")


class EntityAttributeRelationship(BaseModel):
    attribute: HttpUrl
    entityId: str
    state: Optional[str]

    @validator("attribute")
    def name_must_contain_space(cls, v):
        if not re.search("/attr/\w+/value/\w+", v):
            raise ValueError("invalid format")
        return v

    class Config:
        schema_extra = {
            "example": {
                "attribute": "https://opentdf.io/attr/ClassificationUS/value/Unclassified",
                "entityId": "Charlie_1234",
                "state": "active",
            }
        }


class SNSMessageAttribute(BaseModel):
    Value: str
    Type: str
    attribute: HttpUrl


class Entitlements(BaseModel):
    __root__: Dict[
        str,
        Annotated[
            List[str],
            Field(max_length=2000, exclusiveMaximum=2000),
        ],
    ]

    class Config:
        schema_extra = {
            "example": {
                "123e4567-e89b-12d3-a456-426614174000": [
                    "https://opentdf.io/attr/SecurityClearance/value/Unclassified",
                    "https://opentdf.io/attr/OperationalRole/value/Manager",
                    "https://opentdf.io/attr/OperationGroup/value/HR",
                ],
            }
        }


@app.get(
    "/v1/entity/attribute",
    response_model=List[EntityAttributeRelationship],
    include_in_schema=False,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": [
                        {
                            "attribute": "https://opentdf.io/attr/IntellectualProperty/value/TradeSecret",
                            "entityId": "tdf-client",
                            "state": "active",
                        },
                        {
                            "attribute": "https://opentdf.io/attr/ClassificationUS/value/Unclassified",
                            "entityId": "tdf-client",
                            "state": "active",
                        },
                    ]
                }
            }
        }
    },
)
async def read_relationship(auth_token=Depends(get_auth)):
    query = (
        table_entity_attribute.select()
    )  # .where(entity_attribute.c.userid == request.userId)
    result = await database.fetch_all(query)
    relationships: List[EntityAttributeRelationship] = []
    for row in result:
        relationships.append(
            EntityAttributeRelationship(
                attribute=f"{row.get(table_entity_attribute.c.namespace)}/attr/{row.get(table_entity_attribute.c.name)}/value/{row.get(table_entity_attribute.c.value)}",
                entityId=row.get(table_entity_attribute.c.entity_id),
                state="active",
            )
        )
    return relationships


@app.get(
    "/entitlements",
    tags=["Entitlements"],
    response_model=List[Entitlements],
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "123e4567-e89b-12d3-a456-426614174000": [
                            "https://opentdf.io/attr/SecurityClearance/value/Unclassified",
                            "https://opentdf.io/attr/OperationalRole/value/Manager",
                            "https://opentdf.io/attr/OperationGroup/value/HR",
                        ],
                    }
                }
            }
        }
    },
)
async def read_entitlements(
    auth_token=Depends(get_auth),
    authority: Optional[AuthorityUrl] = None,
    name: Optional[str] = None,
    order: Optional[str] = None,
    sort: Optional[str] = Query(
        "",
        regex="^(-*((id)|(state)|(rule)|(name)|(values)),)*-*((id)|(state)|(rule)|(name)|(values))$",
    ),
    db: Session = Depends(get_db),
    pager: Pagination = Depends(Pagination),
):
    filter_args = {}
    if authority:
        filter_args["namespace"] = authority
    if name:
        filter_args["name"] = name
    if order:
        filter_args["values"] = order

    sort_args = sort.split(",") if sort else []

    results = await read_entitlements_crud(
        EntityAttributeSchema, db, filter_args, sort_args
    )

    return pager.paginate(results)


async def read_entitlements_crud(schema, db, filter_args, sort_args):
    results = get_query(schema, db, filter_args, sort_args)
    # logger.debug(query)
    # results = query.all()
    # query = table_entity_attribute.select().order_by(table_entity_attribute.c.entity_id)
    # result = await database.fetch_all(query)
    # must be ordered by entity_id
    entitlements: List[Entitlements] = []
    previous_entity_id: str = ""
    previous_attributes: List[str] = []
    for row in results:
        entity_id: str = row.entity_id
        if not previous_entity_id:
            previous_entity_id = entity_id
        if previous_entity_id != entity_id:
            entitlements.append({previous_entity_id: previous_attributes})
            previous_entity_id = entity_id
            previous_attributes = []
        # add subject attributes
        previous_attributes.append(f"{row.namespace}/attr/{row.name}/value/{row.value}")
    # add last
    if previous_entity_id:
        entitlements.append({previous_entity_id: previous_attributes})

    return entitlements


def parse_attribute_uri(attribute_uri):
    logger.debug(attribute_uri)
    uri = uritools.urisplit(attribute_uri)
    logger.debug(uri)
    logger.debug(uri.authority)
    # workaround for dropping ://
    if not uri.authority:
        uri = uritools.urisplit(attribute_uri.replace(":/", "://"))
        logger.debug(uri)
    path_split_value = uri.path.split("/value/")
    path_split_name = path_split_value[0].split("/attr/")

    if len(path_split_name) == 2 and len(path_split_value) == 2:
        return {
            "namespace": f"{uri.scheme}://{uri.authority}",
            "name": path_split_name[1],
            "value": path_split_value[1],
        }


@app.get(
    "/v1/entity/{entityId}/attribute",
    include_in_schema=False,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": [
                        {
                            "attribute": "https://opentdf.io/attr/IntellectualProperty/value/TradeSecret",
                            "entityId": "tdf-client",
                            "state": "active",
                        },
                        {
                            "attribute": "https://opentdf.io/attr/ClassificationUS/value/Unclassified",
                            "entityId": "tdf-client",
                            "state": "active",
                        },
                    ]
                }
            }
        }
    },
)
async def read_entity_attribute_relationship(
    entityId: str = Path(
        ...,
        example="tdf-client",
    ),
    auth_token=Depends(get_auth),
):
    query = table_entity_attribute.select().where(
        table_entity_attribute.c.entity_id == entityId
    )
    result = await database.fetch_all(query)
    relationships: List[EntityAttributeRelationship] = []
    for row in result:
        relationships.append(
            EntityAttributeRelationship(
                attribute=f"{row.get(table_entity_attribute.c.namespace)}/attr/{row.get(table_entity_attribute.c.name)}/value/{row.get(table_entity_attribute.c.value)}",
                entityId=row.get(table_entity_attribute.c.entity_id),
                state="active",
            )
        )
    return relationships


@app.post(
    "/entitlements/{entityId}",
    tags=["Entitlements"],
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": [
                        "https://opentdf.io/attr/IntellectualProperty/value/TradeSecret",
                        "https://opentdf.io/attr/ClassificationUS/value/Unclassified",
                    ]
                }
            }
        }
    },
)
async def add_entitlements_to_entity(
    entityId: str = Path(
        ...,
        example="tdf-client",
    ),
    request: Annotated[
        List[str],
        Field(max_length=2000, exclusiveMaximum=2000),
    ] = Body(
        ...,
        example=[
            "https://opentdf.io/attr/IntellectualProperty/value/TradeSecret",
            "https://opentdf.io/attr/ClassificationUS/value/Unclassified",
        ],
    ),
    auth_token=Depends(get_auth),
):
    return await add_entitlements_to_entity_crud(entityId, request)


async def add_entitlements_to_entity_crud(entityId, request):
    rows = []
    for attribute_uri in request:
        attribute = parse_attribute_uri(attribute_uri)
        if attribute:
            rows.append(
                {
                    "entity_id": entityId,
                    "namespace": attribute["namespace"],
                    "name": attribute["name"],
                    "value": attribute["value"],
                }
            )
    query = table_entity_attribute.insert(rows)
    await database.execute(query)
    return request


@app.get(
    "/v1/attribute/{attributeURI:path}/entity/",
    include_in_schema=False,
)
async def get_attribute_entity_relationship(
    attributeURI: str, auth_token=Depends(get_auth)
):
    logger.debug(attributeURI)
    attribute = parse_attribute_uri(attributeURI)
    query = table_entity_attribute.select().where(
        and_(
            table_entity_attribute.c.namespace == attribute["namespace"],
            table_entity_attribute.c.name == attribute["name"],
            table_entity_attribute.c.value == attribute["value"],
        )
    )
    result = await database.fetch_all(query)
    relationships: List[EntityAttributeRelationship] = []
    for row in result:
        relationships.append(
            EntityAttributeRelationship(
                attribute=f"{row.get(table_entity_attribute.c.namespace)}/attr/{row.get(table_entity_attribute.c.name)}/value/{row.get(table_entity_attribute.c.value)}",
                entityId=row.get(table_entity_attribute.c.entity_id),
                state="active",
            )
        )
    return relationships


@app.put(
    "/v1/attribute/{attributeURI:path}/entity/",
    include_in_schema=False,
)
async def create_attribute_entity_relationship(
    attributeURI: HttpUrl, request: List[str], auth_token=Depends(get_auth)
):
    attribute = parse_attribute_uri(attributeURI)
    rows = []
    for entity_id in request:
        rows.append(
            {
                "entity_id": entity_id,
                "namespace": attribute["namespace"],
                "name": attribute["name"],
                "value": attribute["value"],
            }
        )
    query = table_entity_attribute.insert(rows)
    await database.execute(query)
    return request


@app.delete(
    "/entitlements/{entityId}",
    tags=["Entitlements"],
    status_code=ACCEPTED,
    responses={
        202: {
            "description": "No Content",
            "content": {"application/json": {"example": {"detail": "Item deleted"}}},
        }
    },
)
async def remove_entitlement_from_entity(
    entityId: str = Path(
        ...,
        example="tdf-client",
    ),
    request: Annotated[
        List[str],
        Field(max_length=2000, exclusiveMaximum=2000),
    ] = Body(
        ...,
        example=[
            "https://opentdf.io/attr/IntellectualProperty/value/TradeSecret",
            "https://opentdf.io/attr/ClassificationUS/value/Unclassified",
        ],
    ),
    auth_token=Depends(get_auth),
):

    return await remove_entitlement_from_entity_crud(entityId, request)


async def remove_entitlement_from_entity_crud(entityId, request):
    attribute_conjunctions = []
    try:
        for item in request:
            attribute = parse_attribute_uri(item)
            attribute_conjunctions.append(
                and_(
                    table_entity_attribute.c.namespace == attribute["namespace"],
                    table_entity_attribute.c.name == attribute["name"],
                    table_entity_attribute.c.value == attribute["value"],
                )
            )

    except IndexError as e:
        raise HTTPException(status_code=BAD_REQUEST, detail=f"invalid: {str(e)}") from e

    await database.execute(
        table_entity_attribute.delete().where(
            and_(
                table_entity_attribute.c.entity_id == entityId,
                or_(*attribute_conjunctions),
            )
        )
    )
    return {}


if __name__ == "__main__":
    print(json.dumps(app.openapi()), file=sys.stdout)
