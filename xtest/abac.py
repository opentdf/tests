import enum
import json
import logging
import subprocess
import sys
import base64

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
    Local: Optional[str] = None
    Remote: Optional[str] = None


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


class KasGrantAttribute(BaseModel):
    attr_id: str
    kas_id: str


class KasGrantValue(BaseModel):
    value_id: str
    kas_id: Optional[str] = None

class KasPublicKeys(BaseModel):
    pem: str
    kid: str
    alg: int

class OpentdfCommandLineTool:

    def __init__(self):
        self.otdfctl = ["sdk/go/otdfctl.sh"]

    def kas_registry_list(self) -> list[KasEntry]:
        cmd = self.otdfctl + "policy kas-registry list".split()
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

    def kas_registry_create(self, url: str, key: str) -> KasEntry:
        cmd = self.otdfctl + "policy kas-registry create".split()
        cmd += [f"--uri={url}"]

        if key.startswith("http"):
            cmd += [f"--public-key-remote={key}"]
        else:
            with open(key, "r") as file:
                keydata = file.read()
                keydatab64 = base64.b64encode(keydata.encode()).decode('utf-8')               
                cmd += [f'--public-keys={{"cached": {{"keys": [{{"pem": "{keydatab64}", "kid": "1", "alg": 1}}]}}}}']
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

    def kas_registry_create_if_not_present(self, uri: str, key: str) -> KasEntry:
        for e in self.kas_registry_list():
            if e.uri == uri:
                return e
        return self.kas_registry_create(uri, key)

    def grant_assign_attr(self, kas: KasEntry, attr: Attribute) -> KasGrantAttribute:
        cmd = self.otdfctl + "policy kas-grants update".split()
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

    def grant_assign_value(
        self, kas: KasEntry, val: AttributeValue
    ) -> KasGrantAttribute:
        cmd = self.otdfctl + "policy kas-grants update".split()
        cmd += [
            f"--kas-id={kas.id}",
            f"--value-id={val.id}",
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

    def grant_unassign_attr(self, kas: KasEntry, attr: Attribute) -> KasGrantAttribute:
        cmd = self.otdfctl + "policy kas-grants remove".split()
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

    def grant_unassign_value(self, kas: KasEntry, val: AttributeValue) -> KasGrantValue:
        cmd = self.otdfctl + "policy kas-grants remove".split()
        cmd += [
            f"--kas-id={kas.id}",
            f"--value-id={val.id}",
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

    def namespace_list(self) -> list[Namespace]:
        cmd = self.otdfctl + "policy attributes namespaces list".split()
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

    def namespace_create(self, name: str) -> Namespace:
        cmd = self.otdfctl + "policy attributes namespaces create".split()
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
        self, namespace: str | Namespace, name: str, t: AttributeRule, values: list[str]
    ) -> Attribute:
        cmd = self.otdfctl + "policy attributes create".split()

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

    def scs_create(self, scs: list[SubjectSet]) -> SubjectConditionSet:
        cmd = self.otdfctl + "policy subject-condition-sets create".split()

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
        self, sc: str | SubjectConditionSet, value: str | AttributeValue
    ) -> SubjectMapping:
        cmd = self.otdfctl + "policy subject-mappings create".split()

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
