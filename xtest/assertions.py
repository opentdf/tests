from pydantic import BaseModel
from typing import Literal


AssertionAlgorithm = Literal["HS256", "RS256"]
Type = Literal["handling", "other"]
Scope = Literal["payload", "tdo"]
AppliesTo = Literal["encrypted", "unencrypted"]
AssertionBindingMethod = Literal["jws"]


class Statement(BaseModel):
    format: str
    schema: str
    value: str


class Binding(BaseModel):
    method: str
    signature: str


class Assertion(BaseModel):
    id: str
    type: Type
    scope: Scope
    appliesToState: AppliesTo
    statement: Statement
    binding: Binding | None = None
