import json
import logging
import os
import re
import sys
from enum import Enum
from http.client import NO_CONTENT
from typing import List, Optional

import databases as databases
import sqlalchemy
import uritools
from fastapi import FastAPI, Request, Depends
from fastapi import Security, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2AuthorizationCodeBearer
from keycloak import KeycloakOpenID
from pydantic import HttpUrl, validator
from pydantic import Json
from pydantic.main import BaseModel
from pydantic import BaseSettings
from sqlalchemy import and_

logging.basicConfig(
    stream=sys.stdout, level=os.getenv("SERVER_LOG_LEVEL", logging.INFO)
)
logger = logging.getLogger(__package__)

swagger_ui_init_oauth = {
    "usePkceWithAuthorizationCodeGrant": True,
    "clientId": os.getenv("OIDC_CLIENT_ID"),
    "realm": os.getenv("OIDC_REALM"),
    "appName": os.getenv("SERVER_PUBLIC_NAME"),
    "scopes": ["email"],
}

class Settings(BaseSettings):
    openapi_url: str = "/openapi.json"

settings = Settings()

app = FastAPI(swagger_ui_init_oauth=swagger_ui_init_oauth, debug=True, openapi_url=settings.openapi_url)

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


async def get_idp_public_key():
    return (
        "-----BEGIN PUBLIC KEY-----\n"
        f"{keycloak_openid.public_key()}"
        "\n-----END PUBLIC KEY-----"
    )


async def get_auth(token: str = Security(oauth2_scheme)) -> Json:
    try:
        return keycloak_openid.decode_token(
            token,
            key=await get_idp_public_key(),
            options={"verify_signature": True, "verify_aud": True, "exp": True},
        )
    except Exception as e:
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

engine = sqlalchemy.create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)


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
    return {"Hello": "World"}


class ProbeType(str, Enum):
    liveness = "liveness"
    readiness = "readiness"


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
                "attribute": "https://eas.local/attr/ClassificationUS/value/Unclassified",
                "entityId": "Charlie_1234",
                "state": "active",
            }
        }


class ClaimsObject(BaseModel):
    attribute: HttpUrl

    class Config:
        schema_extra = {
            "example": {
                "attribute": "https://eas.local/attr/ClassificationUS/value/Unclassified",
            }
        }


@app.get(
    "/v1/entity/attribute",
    response_model=List[EntityAttributeRelationship],
    dependencies=[Depends(get_auth)],
)
async def read_relationship():
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
    "/v1/entity/claimsobject",
    response_model=List[ClaimsObject],
    dependencies=[Depends(get_auth)],
)
async def read_relationship():
    query = (
        table_entity_attribute.select()
    )  # .where(entity_attribute.c.userid == request.userId)
    result = await database.fetch_all(query)
    claimsobject: List[ClaimsObject] = []
    for row in result:
        claimsobject.append(
            ClaimsObject(
                attribute=f"{row.get(table_entity_attribute.c.namespace)}/attr/{row.get(table_entity_attribute.c.name)}/value/{row.get(table_entity_attribute.c.value)}",
            )
        )
    return claimsobject


def parse_attribute_uri(attribute_uri):
    # FIXME harden, unit test
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

    return {
        "namespace": f"{uri.scheme}://{uri.authority}",
        "name": path_split_name[1],
        "value": path_split_value[1],
    }


@app.get("/v1/entity/{entityId}/attribute", dependencies=[Depends(get_auth)])
async def read_entity_attribute_relationship(entityId: str):
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


@app.get("/v1/entity/{entityId}/claimsobject", dependencies=[Depends(get_auth)])
async def read_entity_attribute_relationship(entityId: str):
    query = table_entity_attribute.select().where(
        table_entity_attribute.c.entity_id == entityId
    )
    result = await database.fetch_all(query)
    claimsobject: List[ClaimsObject] = []
    for row in result:
        claimsobject.append(
            ClaimsObject(
                attribute=f"{row.get(table_entity_attribute.c.namespace)}/attr/{row.get(table_entity_attribute.c.name)}/value/{row.get(table_entity_attribute.c.value)}",
            )
        )
    return claimsobject


@app.put("/v1/entity/{entityId}/attribute", dependencies=[Depends(get_auth)])
async def create_entity_attribute_relationship(entityId: str, request: List[HttpUrl]):
    rows = []
    for attribute_uri in request:
        attribute = parse_attribute_uri(attribute_uri)
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


@app.get("/v1/attribute/{attributeURI:path}/entity/", dependencies=[Depends(get_auth)])
async def get_attribute_entity_relationship(attributeURI: str):
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


@app.put("/v1/attribute/{attributeURI:path}/entity/", dependencies=[Depends(get_auth)])
async def create_attribute_entity_relationship(
    attributeURI: HttpUrl, request: List[str]
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
    "/v1/entity/{entityId}/attribute/{attributeURI:path}",
    status_code=204,
    dependencies=[Depends(get_auth)],
)
async def delete_attribute_entity_relationship(entityId: str, attributeURI: HttpUrl):
    attribute = parse_attribute_uri(attributeURI)
    statement = table_entity_attribute.delete().where(
        and_(
            table_entity_attribute.c.entity_id == entityId,
            table_entity_attribute.c.namespace == attribute["namespace"],
            table_entity_attribute.c.name == attribute["name"],
            table_entity_attribute.c.value == attribute["value"],
        )
    )
    await database.execute(statement)


if __name__ == "__main__":
    print(json.dumps(app.openapi()), file=sys.stdout)
