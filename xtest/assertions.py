from pydantic import BaseModel
from typing import Literal


Type = Literal["handling", "other"]
Scope = Literal["payload", "tdo"]
AppliesTo = Literal["encrypted", "unencrypted"]
BindingMethod = Literal["jws"]


class Statement(BaseModel):
    format: str
    schema: str
    value: str


class Binding(BaseModel):
    method: BindingMethod
    signature: str


class Assertion(BaseModel):
    id: str
    type: Type
    scope: Scope
    appliesToState: AppliesTo
    statement: Statement
    binding: Binding | None = None
