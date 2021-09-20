import os
import re
from enum import Enum
from typing import List, Optional

import databases as databases
import sqlalchemy
import uritools
from fastapi import FastAPI, Request
from pydantic import HttpUrl, validator
from pydantic.main import BaseModel
from sqlalchemy import and_

app = FastAPI()

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


@app.get("/v1/entity/attribute", response_model=List[EntityAttributeRelationship])
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

@app.get("/v1/entity/claimsobject", response_model=List[ClaimsObject])
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
    uri = uritools.urisplit(attribute_uri)
    path_split_value = uri.path.split("/value/")
    path_split_name = path_split_value[0].split("/attr/")
    return {
        "namespace": f"{uri.scheme}://{uri.authority}",
        "name": path_split_name[1],
        "value": path_split_value[1],
    }


@app.get("/v1/entity/{entityId}/attribute")
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

@app.get("/v1/entity/{entityId}/claimsobject")
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


@app.put("/v1/entity/{entityId}/attribute")
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


@app.put("/v1/attribute/{attributeURI:path}/entity/")
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


@app.delete("/v1/entity/{entityId}/attribute/{attributeURI:path}", status_code=204)
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
