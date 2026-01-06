import enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BaseModelIgnoreExtra(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Timestamp(BaseModelIgnoreExtra):
    seconds: int
    nanos: int


class Metadata(BaseModelIgnoreExtra):
    created_at: Timestamp
    updated_at: Timestamp
    labels: list[str] | None = None


class BoolValue(BaseModelIgnoreExtra):
    value: bool


class Namespace(BaseModelIgnoreExtra):
    id: str
    name: str
    fqn: str
    active: BoolValue | None = None
    metadata: Metadata | None = None


class AttributeRule(enum.IntEnum):
    ALL_OF = 1
    ANY_OF = 2
    HIERARCHY = 3


class AttributeValue(BaseModelIgnoreExtra):
    id: str
    value: str
    fqn: str | None = None
    active: BoolValue | None = None
    metadata: Metadata | None = None


class Attribute(BaseModelIgnoreExtra):
    id: str
    namespace: Namespace
    name: str
    rule: AttributeRule
    values: list[AttributeValue] | None = None
    fqn: str | None
    active: BoolValue | None = None
    metadata: Metadata | None = None

    @property
    def value_fqns(self) -> list[str]:
        if not self.values:
            return []
        v = [v.fqn for v in self.values if v.fqn]
        assert len(v) == len(self.values)
        return v


class SubjectMappingOperatorEnum(enum.IntEnum):
    IN = 1
    NOT_IN = 2
    IN_CONTAINS = 3


class Condition(BaseModelIgnoreExtra):
    subject_external_selector_value: str
    operator: SubjectMappingOperatorEnum
    subject_external_values: list[str]


class ConditionBooleanTypeEnum(enum.IntEnum):
    AND = 1
    OR = 2


class ConditionGroup(BaseModelIgnoreExtra):
    boolean_operator: ConditionBooleanTypeEnum
    conditions: list[Condition]


class SubjectSet(BaseModelIgnoreExtra):
    condition_groups: list[ConditionGroup]


class SubjectConditionSet(BaseModelIgnoreExtra):
    id: str
    subject_sets: list[SubjectSet]
    active: BoolValue | None = None
    metadata: Metadata | None = None


class StandardAction(enum.IntEnum):
    DECRYPT = 1
    TRANSMIT = 2


class SubjectAction(BaseModelIgnoreExtra):
    Standard: StandardAction | None = None
    Custom: str | None = None


class Action(BaseModelIgnoreExtra):
    Value: SubjectAction | None = None
    id: str | None = None
    name: str | None = None


class SubjectMapping(BaseModelIgnoreExtra):
    id: str
    attribute_value: AttributeValue
    subject_condition_set: SubjectConditionSet
    actions: list[Action]
    metadata: Metadata | None = None


class NamespaceKey(BaseModelIgnoreExtra):
    namespace_id: str
    key_id: str


# Deprecated
class KasGrantNamespace(BaseModelIgnoreExtra):
    namespace_id: str
    key_access_server_id: str | None = None


class AttributeKey(BaseModelIgnoreExtra):
    attribute_id: str
    key_id: str


# Deprecated
class KasGrantAttribute(BaseModelIgnoreExtra):
    attribute_id: str
    key_access_server_id: str | None = None


class ValueKey(BaseModelIgnoreExtra):
    value_id: str
    key_id: str


# Deprecated
class KasGrantValue(BaseModelIgnoreExtra):
    value_id: str
    key_access_server_id: str | None = None


KAS_PUBLIC_KEY_ALG_ENUM_RSA_2048 = 1
KAS_PUBLIC_KEY_ALG_ENUM_RSA_4096 = 2

KAS_PUBLIC_KEY_ALG_ENUM_EC_SECP256R1 = 5
KAS_PUBLIC_KEY_ALG_ENUM_EC_SECP384R1 = 6
KAS_PUBLIC_KEY_ALG_ENUM_EC_SECP521R1 = 7


_KAS_ALG_TO_STR_MAP = {
    KAS_PUBLIC_KEY_ALG_ENUM_RSA_2048: "rsa:2048",
    KAS_PUBLIC_KEY_ALG_ENUM_RSA_4096: "rsa:4096",
    KAS_PUBLIC_KEY_ALG_ENUM_EC_SECP256R1: "ec:secp256r1",
    KAS_PUBLIC_KEY_ALG_ENUM_EC_SECP384R1: "ec:secp384r1",
    KAS_PUBLIC_KEY_ALG_ENUM_EC_SECP521R1: "ec:secp521r1",
}
_STR_TO_KAS_ALG_MAP = {v: k for k, v in _KAS_ALG_TO_STR_MAP.items()}


def kas_public_key_alg_to_str(alg: int | None) -> str | None:
    if alg is None:
        return None
    try:
        return _KAS_ALG_TO_STR_MAP[alg]
    except KeyError:
        raise ValueError(f"Unknown KAS public key algorithm: {alg}") from None


def str_to_kas_public_key_alg(alg_str: str | None) -> int | None:
    if alg_str is None:
        return None
    try:
        return _STR_TO_KAS_ALG_MAP[alg_str]
    except KeyError:
        raise ValueError(f"Unknown KAS public key algorithm string: {alg_str}")


class KasPublicKey(BaseModelIgnoreExtra):
    pem: str
    kid: str
    alg: int | None = None
    algStr: str | None = Field(default=None, exclude=True)


# Helper model for the structure within key.public_key_ctx in the KAS key creation response
class KasKeyResponsePublicKeyContext(BaseModelIgnoreExtra):
    pem: str


# Helper model for the nested "key" object in the KAS key creation response
class KasKeyResponseKeyDetails(BaseModelIgnoreExtra):
    id: str
    key_id: str
    key_algorithm: int
    key_status: int
    key_mode: int
    public_key_ctx: KasKeyResponsePublicKeyContext
    legacy: bool = False
    metadata: Metadata | None = None


class KasKey(BaseModelIgnoreExtra):
    kas_id: str
    key: KasKeyResponseKeyDetails
    kas_uri: str


class KasPublicKeySet(BaseModelIgnoreExtra):
    keys: list[KasPublicKey]


class PublicKey(BaseModelIgnoreExtra):
    remote: str | None = None
    cached: KasPublicKeySet | None = None


class PublicKeyChoice(BaseModelIgnoreExtra):
    PublicKey: PublicKey | None


class KasEntry(BaseModelIgnoreExtra):
    id: str
    uri: str
    public_key: PublicKeyChoice | None
    metadata: Metadata | None = None


class PolicyEnforcementPoint(BaseModelIgnoreExtra):
    client_id: str | None = None


class ObligationRequestContext(BaseModelIgnoreExtra):
    pep: PolicyEnforcementPoint | None = None


class ObligationTrigger(BaseModelIgnoreExtra):
    id: str
    action: Action
    attribute_value: AttributeValue
    obligation_value: Optional["ObligationValue"] = None
    context: list[ObligationRequestContext] | ObligationRequestContext | None = None
    metadata: Metadata | None = None


class ObligationValue(BaseModelIgnoreExtra):
    id: str
    obligation: Optional["Obligation"] = None
    value: str
    triggers: Optional[list["ObligationTrigger"]] = None
    fqn: str | None = None
    metadata: Metadata | None = None


class Obligation(BaseModelIgnoreExtra):
    id: str
    namespace: Namespace
    name: str
    values: Optional[list["ObligationValue"]] = None
    fqn: str | None = None
    metadata: Metadata | None = None
