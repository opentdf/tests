import enum
import json
import logging
import random
import string
import subprocess
import sys

from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)


class Timestamp(BaseModel):
    seconds: int
    nanos: int


class Metadata(BaseModel):
    created_at: Timestamp
    updated_at: Timestamp
    labels: Optional[list[str]] = None


class BoolValue(BaseModel):
    value: bool


class Namespace(BaseModel):
    id: str
    name: str
    fqn: str
    active: Optional[BoolValue] = None
    metadata: Optional[Metadata] = None


class AttributeRule(enum.IntEnum):
    ALL_OF = 1
    ANY_OF = 2
    HIERARCHY = 3


class AttributeValue(BaseModel):
    id: str
    value: str
    fqn: Optional[str] = None
    active: Optional[BoolValue] = None
    metadata: Optional[Metadata] = None


class Attribute(BaseModel):
    id: str
    namespace: Namespace
    name: str
    rule: AttributeRule
    values: Optional[list[AttributeValue]] = None
    fqn: Optional[str]
    active: Optional[BoolValue] = None
    metadata: Optional[Metadata] = None


class SubjectMappingOperatorEnum(enum.IntEnum):
    IN = 1
    NOT_IN = 2
    IN_CONTAINS = 3


class Condition(BaseModel):
    subject_external_selector_value: str
    operator: SubjectMappingOperatorEnum
    subject_external_values: list[str]


class ConditionBooleanTypeEnum(enum.IntEnum):
    AND = 1
    OR = 2


class ConditionGroup(BaseModel):
    boolean_operator: ConditionBooleanTypeEnum
    conditions: list[Condition]


class SubjectSet(BaseModel):
    condition_groups: list[ConditionGroup]


class SubjectConditionSet(BaseModel):
    id: str
    subject_sets: list[SubjectSet]
    active: Optional[BoolValue] = None
    metadata: Optional[Metadata] = None


class StandardAction(enum.IntEnum):
    DECRYPT = 1
    TRANSMIT = 2


class SubjectAction(BaseModel):
    Standard: Optional[StandardAction] = None
    Custom: Optional[str] = None


# Huh? Is this a side effect of the oneof value field?
class Action(BaseModel):
    Value: SubjectAction


class PublicKey(BaseModel):
    Local: Optional[str]
    Remote: Optional[str]

class PublicKeyChoice(BaseModel):
    PublicKey: PublicKey

class KasEntry(BaseModel):
    id: str
    uri: str
    public_key: Optional[PublicKeyChoice]
    metadata: Optional[Metadata] = None


class SubjectMapping(BaseModel):
    id: str
    attribute_value: AttributeValue
    subject_condition_set: SubjectConditionSet
    actions: list[Action]
    metadata: Optional[Metadata] = None


def kas_registry_list(otdfctl) -> list[KasEntry]:
    cmd = otdfctl + "policy kas-registry list".split()
    logger.info(f"kr-ls [{' '.join(cmd)}]")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    code = process.wait()
    out, err = process.communicate()
    if err:
        print(err, file=sys.stderr)
    if out:
        print(out)
    assert code == 0
    return [KasEntry(**n) for n in json.loads(out)]


def kas_registry_create(otdfctl, url: str, key: str) -> KasEntry:
    cmd = otdfctl + "policy kas-registry create".split()
    cmd += [f"--uri={url}"]

    if key.startswith("http"):
        cmd += [f"--public-key-remote={key}"]
    else:
        with open(key, 'r') as file:
            keydata = file.read()
            cmd += [f"--public-key-local={keydata}"]


    logger.info(f"kr-create [{' '.join(cmd)}]")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    code = process.wait()
    out, err = process.communicate()
    if err:
        print(err, file=sys.stderr)
    if out:
        print(out)
    assert code == 0
    return KasEntry.model_validate_json(out)


def kas_registry_create_if_not_present(otdfctl, uri: str, key: str) -> KasEntry:
    for e in kas_registry_list(otdfctl):
        if e.uri == uri:
            return e
    return kas_registry_create(otdfctl, uri, key)


class KasGrantAttribute(BaseModel):
    attr_id: str
    kas_id: str

class KasGrantValue(BaseModel):
    val_id: str
    kas_id: str

def grant_assign_attr(otdfctl, kas: KasEntry, attr: Attribute) -> KasGrantAttribute:
    cmd = otdfctl + "policy kas-grants update".split()
    cmd += [
        f"--kas-id={kas.id}",
        f"--attribute-id={attr.id}",
    ]
    logger.info(f"grant-update [{' '.join(cmd)}]")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    code = process.wait()
    out, err = process.communicate()
    if err:
        print(err, file=sys.stderr)
    if out:
        print(out)
    assert code == 0
    return KasGrantAttribute.model_validate_json(out)

def grant_assign_value(otdfctl, kas: KasEntry, attr: Attribute) -> KasGrantAttribute:
    cmd = otdfctl + "policy kas-grants update".split()
    cmd += [
        f"--kas-id={kas.id}",
        f"--value-id={attr.id}",
    ]
    logger.info(f"grant-update [{' '.join(cmd)}]")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    code = process.wait()
    out, err = process.communicate()
    if err:
        print(err, file=sys.stderr)
    if out:
        print(out)
    assert code == 0
    return KasGrantValue.model_validate_json(out)


def grant_unassign_attr(otdfctl, kas: KasEntry, attr: Attribute) -> KasGrantAttribute:
    cmd = otdfctl + "policy kas-grants remove".split()
    cmd += [
        f"--kas-id={kas.id}",
        f"--attribute-id={attr.id}",
    ]
    logger.info(f"grant-update [{' '.join(cmd)}]")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    code = process.wait()
    out, err = process.communicate()
    if err:
        print(err, file=sys.stderr)
    if out:
        print(out)
    assert code == 0
    return KasGrantAttribute.model_validate_json(out)

def grant_unassign_value(otdfctl, kas: KasEntry, attr: Attribute) -> KasGrantValue:
    cmd = otdfctl + "policy kas-grants remove".split()
    cmd += [
        f"--kas-id={kas.id}",
        f"--value-id={attr.id}",
    ]
    logger.info(f"grant-update [{' '.join(cmd)}]")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    code = process.wait()
    out, err = process.communicate()
    if err:
        print(err, file=sys.stderr)
    if out:
        print(out)
    assert code == 0
    return KasGrantValue.model_validate_json(out)



def namespace_list(otdfctl) -> list[Namespace]:
    cmd = otdfctl + "policy attributes namespaces list".split()
    logger.info(f"ns-ls [{' '.join(cmd)}]")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    code = process.wait()
    out, err = process.communicate()
    if err:
        print(err, file=sys.stderr)
    if out:
        print(out)
    assert code == 0
    return [Namespace(**n) for n in json.loads(out)]


def namespace_create(otdfctl, name: str) -> Namespace:
    cmd = otdfctl + "policy attributes namespaces create".split()
    cmd += [f"--name={name}"]
    logger.info(f"ns-create [{' '.join(cmd)}]")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    code = process.wait()
    out, err = process.communicate()
    if err:
        print(err, file=sys.stderr)
    if out:
        print(out)
    assert code == 0
    return Namespace.model_validate_json(out)


def attribute_create(
    otdfctl, namespace: str | Namespace, name: str, t: AttributeRule, values: list[str]
) -> Attribute:
    cmd = otdfctl + "policy attributes create".split()

    cmd += [
        f"--namespace={namespace if isinstance(namespace, str) else namespace.id}",
        f"--name={name}",
        f"--rule={t.name}",
    ]
    if values:
        cmd += [f"--value={','.join(values)}"]
    logger.info(f"attr-create [{' '.join(cmd)}]")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    code = process.wait()
    out, err = process.communicate()
    if err:
        print(err, file=sys.stderr)
    if out:
        print(out)
    assert code == 0
    return Attribute.model_validate_json(out)


def scs_create(otdfctl, scs: list[SubjectSet]) -> SubjectConditionSet:
    cmd = otdfctl + "policy subject-condition-sets create".split()

    cmd += [f"--subject-sets=[{','.join([s.model_dump_json() for s in scs])}]"]

    logger.info(f"scs-create [{' '.join(cmd)}]")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    code = process.wait()
    out, err = process.communicate()
    if err:
        print(err, file=sys.stderr)
    if out:
        print(out)
    assert code == 0
    return SubjectConditionSet.model_validate_json(out)


def scs_map(
    otdfctl, sc: str | SubjectConditionSet, value: str | AttributeValue
) -> SubjectMapping:
    cmd = otdfctl + "policy subject-mappings create".split()

    cmd += [
        "--action-standard=DECRYPT",
        f"--attribute-value-id={value if isinstance(sc, str) else value.id}",
        f"--subject-condition-set-id={sc if isinstance(sc, str) else sc.id}",
    ]

    logger.info(f"sm-create [{' '.join(cmd)}]")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    code = process.wait()
    out, err = process.communicate()
    if err:
        print(err, file=sys.stderr)
    if out:
        print(out)
    assert code == 0
    return SubjectMapping.model_validate_json(out)


def test_namespaces_list(otdfctl):
    ns = namespace_list(otdfctl)
    assert len(ns) >= 4


def test_attribute_create(otdfctl):
    random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"
    ns = namespace_create(otdfctl, random_ns)
    anyof = attribute_create(otdfctl, ns, "free", AttributeRule.ANY_OF, ["1", "2", "3"])
    allof = attribute_create(
        otdfctl, ns, "strict", AttributeRule.ALL_OF, ["1", "2", "3"]
    )
    assert anyof != allof


def test_scs_create(otdfctl):
    c = Condition(
        subject_external_selector_value=".clientId",
        operator=SubjectMappingOperatorEnum.IN,
        subject_external_values=["opentdf-sdk"],
    )
    cg = ConditionGroup(boolean_operator=ConditionBooleanTypeEnum.OR, conditions=[c])

    sc = scs_create(
        otdfctl,
        [SubjectSet(condition_groups=[cg])],
    )
    assert len(sc.subject_sets) == 1


def test_create_and_assign_attr(otdfctl):
    # Create a new attribute in a random namespace
    random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"
    ns = namespace_create(otdfctl, random_ns)
    anyof = attribute_create(
        otdfctl, ns, "letra", AttributeRule.ANY_OF, ["alpha", "beta", "gamma"]
    )
    alpha, beta, gamma = anyof.values
    assert alpha.name == "alpha"
    assert beta.name == "beta"
    assert gamma.name == "gamma"

    # Then assign it to all clientIds = opentdf-sdk
    sc = scs_create(
        otdfctl,
        [
            SubjectSet(
                condition_groups=[
                    ConditionGroup(
                        boolean_operator=ConditionBooleanTypeEnum.OR,
                        conditions=[
                            Condition(
                                subject_external_selector_value=".clientId",
                                operator=SubjectMappingOperatorEnum.IN,
                                subject_external_values=["opentdf-sdk"],
                            )
                        ],
                    )
                ]
            )
        ],
    )
    sm = scs_map(otdfctl, sc, alpha)
    assert sm.attribute_value.value == "alpha"
    # Now assign it to the current KAS
    kas_entry = kas_registry_create_if_not_present(otdfctl, "http://localhost:8080", "../platform/kas-cert.pem")
    grant_assign_value(otdfctl, kas_entry, alpha)

    # We have a grant for alpha to localhost kas. Now try to use it...
    # TODO 
