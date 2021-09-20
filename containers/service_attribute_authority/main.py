import logging
import os
from enum import Enum
from typing import Optional, List

import databases as databases
import sqlalchemy
from asyncpg import UniqueViolationError
from fastapi import FastAPI, Request, HTTPException
from pydantic import HttpUrl, ValidationError
from pydantic.main import BaseModel

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

table_authority_namespace = sqlalchemy.Table(
    "attribute_namespace",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("name", sqlalchemy.VARCHAR),
)

table_attribute = sqlalchemy.Table(
    "attribute",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column(
        "namespace_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("attribute_namespace.id"),
    ),
    sqlalchemy.Column("state", sqlalchemy.Integer),
    sqlalchemy.Column("rule", sqlalchemy.VARCHAR),
    sqlalchemy.Column("name", sqlalchemy.VARCHAR),
    sqlalchemy.Column("description", sqlalchemy.VARCHAR),
    sqlalchemy.Column("values", sqlalchemy.ARRAY(sqlalchemy.TEXT)),
)

engine = sqlalchemy.create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)


@app.middleware("http")
async def add_response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


class AttributeRuleType(str, Enum):
    hierarchy = "hierarchy"
    anyOf = "anyOf"
    allOf = "allOf"


class Attribute(BaseModel):
    authorityNamespace: HttpUrl
    name: str
    order: list
    rule: AttributeRuleType
    state: Optional[str]

    class Config:
        schema_extra = {
            "example": {
                "authorityNamespace": "https://eas.local",
                "name": "IntellectualProperty",
                "rule": "hierarchy",
                "state": "published",
                "values": ["TradeSecret", "Proprietary", "BusinessSensitive", "Open"],
                "order": ["TradeSecret", "Proprietary", "BusinessSensitive", "Open"],
            }
        }


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


@app.get("/v1/attr", response_model=List[Attribute])
async def read_attribute():
    query = table_attribute.select()
    result = await database.fetch_all(query)
    attributes: List[Attribute] = []
    for row in result:
        try:
            attributes.append(
                Attribute(
                    authorityNamespace=row.get(table_attribute.c.namespace_id),
                    name=row.get(table_attribute.c.name),
                    order=row.get("values"),
                    values=row.get("values"),
                    rule=row.get(table_attribute.c.rule),
                    state=row.get(table_attribute.c.state),
                )
            )
        except ValidationError as e:
            logging.error(e)
    return attributes


@app.post("/v1/attrName", response_model=List[Attribute])
async def read_attribute():
    # return all for now body: List[HttpUrl]
    query = table_attribute.select()
    result = await database.fetch_all(query)
    attributes: List[Attribute] = []
    for row in result:
        try:
            attributes.append(
                Attribute(
                    authorityNamespace=row.get(table_attribute.c.namespace_id),
                    name=row.get(table_attribute.c.name),
                    order=row.get("values"),
                    values=row.get("values"),
                    rule=row.get(table_attribute.c.rule),
                    state=row.get(table_attribute.c.state),
                )
            )
        except ValidationError as e:
            logging.error(e)
    return attributes


@app.post("/v1/attr", response_model=Attribute)
async def create_attribute(request: Attribute):
    # lookup
    query = table_authority_namespace.select().where(
        table_authority_namespace.c.name == request.authorityNamespace
    )
    result = await database.fetch_one(query)
    if result:
        namespace_id = result.get(table_authority_namespace.c.id)
        # insert
        query = table_attribute.insert().values(
            name=request.name,
            namespace_id=namespace_id,
            state=1,
            rule=1,
            values=request.order,
        )
        try:
            await database.execute(query)
        except UniqueViolationError as e:
            raise HTTPException(status_code=400, detail=f"duplicate: {str(e)}") from e
    return request


@app.get("/v1/authorityNamespace")
async def read_authority_namespace():
    query = (
        table_authority_namespace.select()
    )  # .where(entity_attribute.c.userid == request.userId)
    result = await database.fetch_all(query)
    namespaces = []
    for row in result:
        namespaces.append(f"{row.get(table_authority_namespace.c.name)}")
    return namespaces


@app.post("/v1/authorityNamespace")
async def create_authority_namespace(request_authority_namespace: HttpUrl):
    # insert
    query = table_authority_namespace.insert().values(name=request_authority_namespace)
    try:
        await database.execute(query)
    except UniqueViolationError as e:
        raise HTTPException(status_code=400, detail=f"duplicate: {str(e)}") from e
    # select all
    query = (
        table_authority_namespace.select()
    )  # .where(entity_attribute.c.userid == request.userId)
    result = await database.fetch_all(query)
    namespaces = []
    for row in result:
        namespaces.append(f"{row.get(table_authority_namespace.c.name)}")
    return namespaces
