import json
import os
import sys
from enum import Enum
from http.client import NO_CONTENT
from typing import List, Optional

import databases as databases
import sqlalchemy
from fastapi import FastAPI, Request
from pydantic import EmailStr
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

table_entity = sqlalchemy.Table(
    "entity",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("is_person", sqlalchemy.BOOLEAN),
    sqlalchemy.Column("state", sqlalchemy.INTEGER),
    sqlalchemy.Column("entity_id", sqlalchemy.VARCHAR),
    sqlalchemy.Column("name", sqlalchemy.VARCHAR),
    sqlalchemy.Column("email", sqlalchemy.VARCHAR),
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


class Entity(BaseModel):
    userId: str
    name: Optional[str]
    email: Optional[EmailStr]
    nonPersonEntity: bool = True
    state: Optional[str] = "active"
    pubKey: Optional[str] = ""
    attributes: List[str] = []

    class Config:
        schema_extra = {
            "example": {
                "userId": "bob_5678",
                "email": "bob@eas.local",
                "name": "Bob",
                "nonPersonEntity": False,
            }
        }


@app.get("/v1/entity")
async def read_entity():
    query = table_entity.select()  # .where(entity_attribute.c.userid == request.userId)
    result = await database.fetch_all(query)
    entities: List[Entity] = []
    for row in result:
        entities.append(
            Entity(
                userId=row.get(table_entity.c.entity_id),
                name=row.get(table_entity.c.name),
                email=row.get(table_entity.c.email),
                state=row.get(table_entity.c.state),
            )
        )
    return entities


@app.get("/v1/entity/{entityId}")
async def read_entity_by_id(entityId: str):
    query = table_entity.select().where(table_entity.c.entity_id == entityId)
    result = await database.fetch_one(query)
    if result:
        return Entity(
            userId=result.get(table_entity.c.entity_id),
            name=result.get(table_entity.c.name),
            email=result.get(table_entity.c.email),
            state=result.get(table_entity.c.state),
        )


@app.post("/v1/entity")
async def create_entity(request: Entity):
    query = table_entity.insert().values(
        is_person=request.nonPersonEntity,
        state=1,
        entity_id=request.userId,
        name=request.name,
        email=request.email,
    )
    result = await database.execute(query)
    if result:
        return request


if __name__ == "__main__":
    print(json.dumps(app.openapi()), file=sys.stdout)
