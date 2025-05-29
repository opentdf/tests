from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


Type = Literal["handling", "other"]
Scope = Literal["payload", "tdo"]
AppliesTo = Literal["encrypted", "unencrypted"]
BindingMethod = Literal["jws", "JWS"]


class Statement(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    format: str
    schema_: str = Field(..., alias="schema")
    value: str | dict[str, str]


class Binding(BaseModel):
    method: BindingMethod
    signature: str


class AssertionKey(BaseModel):
    alg: str
    key: str


class Assertion(BaseModel):
    id: str
    type: Type
    scope: Scope
    appliesToState: AppliesTo
    statement: Statement
    binding: Binding | None = None
    signingKey: AssertionKey | None = None


class AssertionVerificationKeys(BaseModel):
    keys: dict[str, AssertionKey]
