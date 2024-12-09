from pydantic import BaseModel
from typing import Literal, Union, Optional, Dict


Type = Literal["handling", "other"]
Scope = Literal["payload", "tdo"]
AppliesTo = Literal["encrypted", "unencrypted"]
BindingMethod = Literal["jws"]


class Statement(BaseModel):
    format: str
    schema: str
    value: Union[str, dict]


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
    keys: Dict[str, AssertionKey]
