import enum
import json
import logging
import subprocess
import sys

from pydantic import BaseModel

logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)


class Timestamp(BaseModel):
    seconds: int
    nanos: int


class Metadata(BaseModel):
    created_at: Timestamp
    updated_at: Timestamp
    labels: list[str] | None = None


class BoolValue(BaseModel):
    value: bool


class Namespace(BaseModel):
    id: str
    name: str
    fqn: str
    active: BoolValue | None = None
    metadata: Metadata | None = None


class AttributeRule(enum.IntEnum):
    ALL_OF = 1
    ANY_OF = 2
    HIERARCHY = 3


class AttributeValue(BaseModel):
    id: str
    value: str
    fqn: str | None = None
    active: BoolValue | None = None
    metadata: Metadata | None = None


class Attribute(BaseModel):
    id: str
    namespace: Namespace
    name: str
    rule: AttributeRule
    values: list[AttributeValue] | None = None
    fqn: str | None
    active: BoolValue | None = None
    metadata: Metadata | None = None


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
    active: BoolValue | None = None
    metadata: Metadata | None = None


class StandardAction(enum.IntEnum):
    DECRYPT = 1
    TRANSMIT = 2


class SubjectAction(BaseModel):
    Standard: StandardAction | None = None
    Custom: str | None = None


# Huh? Is this a side effect of the oneof value field?
class Action(BaseModel):
    Value: SubjectAction


class SubjectMapping(BaseModel):
    id: str
    attribute_value: AttributeValue
    subject_condition_set: SubjectConditionSet
    actions: list[Action]
    metadata: Metadata | None = None

class KasGrantNamespace(BaseModel):
    ns_id: str
    kas_id: str

class KasGrantAttribute(BaseModel):
    attr_id: str
    kas_id: str


class KasGrantValue(BaseModel):
    value_id: str
    kas_id: str | None = None


KAS_PUBLIC_KEY_ALG_ENUM_RSA_2048 = 1
KAS_PUBLIC_KEY_ALG_ENUM_EC_SECP256R1 = 5


class KasPublicKey(BaseModel):
    pem: str
    kid: str
    alg: int


class KasPublicKeySet(BaseModel):
    keys: list[KasPublicKey]


class PublicKey(BaseModel):
    local: str | None = None
    remote: str | None = None
    cached: KasPublicKeySet | None = None


class PublicKeyChoice(BaseModel):
    PublicKey: PublicKey


class KasEntry(BaseModel):
    id: str
    uri: str
    public_key: PublicKeyChoice | None
    metadata: Metadata | None = None


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
        o = json.loads(out)
        if not o:
            return []
        return [KasEntry(**n) for n in o]

    def kas_registry_create(
        self,
        url: str,
        public_key: PublicKey,
    ) -> KasEntry:
        cmd = self.otdfctl + "policy kas-registry create".split()
        cmd += [f"--uri={url}"]
        cmd += [f"--public-keys={public_key.model_dump_json()}"]
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

    def kas_registry_create_if_not_present(self, uri: str, key: PublicKey) -> KasEntry:
        for e in self.kas_registry_list():
            if e.uri == uri:
                return e
        return self.kas_registry_create(uri, key)
    
    def grant_assign_ns(self, kas: KasEntry, ns: Namespace) -> KasGrantNamespace:
        cmd = self.otdfctl + "policy kas-grants assign".split()
        cmd += [
            f"--kas-id={kas.id}",
            f"--namespace-id={ns.id}",
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
        return KasGrantNamespace.model_validate_json(out)

    def grant_assign_attr(self, kas: KasEntry, attr: Attribute) -> KasGrantAttribute:
        cmd = self.otdfctl + "policy kas-grants assign".split()
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

    def grant_assign_value(self, kas: KasEntry, val: AttributeValue) -> KasGrantValue:
        cmd = self.otdfctl + "policy kas-grants assign".split()
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
    
    def grant_unassign_ns(self, kas: KasEntry, ns: Namespace) -> KasGrantNamespace:
        cmd = self.otdfctl + "policy kas-grants unassign".split()
        cmd += [
            f"--kas-id={kas.id}",
            f"--namespace-id={ns.id}",
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
        return KasGrantNamespace.model_validate_json(out)

    def grant_unassign_attr(self, kas: KasEntry, attr: Attribute) -> KasGrantAttribute:
        cmd = self.otdfctl + "policy kas-grants unassign".split()
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
        cmd = self.otdfctl + "policy kas-grants unassign".split()
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
        o = json.loads(out)
        if not o:
            return []
        return [Namespace(**n) for n in o]

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
            f"--attribute-value-id={value if isinstance(value, str) else value.id}",
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
