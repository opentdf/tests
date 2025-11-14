import enum
import json
import logging
import os
import subprocess
import sys
import base64
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)


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


class OpentdfCommandLineTool:
    # Flag to indicate we are using an older version of policy subject-mappings create that uses the `action-standard` flag
    # instead of just `action`
    flag_scs_map_action_standard: bool = False

    def __init__(self, otdfctl_path: str | None = None):
        path = otdfctl_path if otdfctl_path else "sdk/go/otdfctl.sh"
        if not os.path.isfile(path):
            raise FileNotFoundError(f"otdfctl.sh not found at path: {path}")
        self.otdfctl = [path]

    def _b64_pem(pem: str | None) -> str | None:
        if pem is None:
            return None

        s = pem.strip()
        try:
            _ = base64.b64decode(s, validate=True)
            return s
        except Exception:
            return base64.b64encode(s.encode("utf-8")).decode("utf-8")

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
        if isinstance(o, dict):
            o = o.get("key_access_servers", [])
        return [KasEntry(**n) for n in o]

    def kas_registry_create(
        self,
        url: str,
        public_key: PublicKey | None = None,
    ) -> KasEntry:
        cmd = self.otdfctl + "policy kas-registry create".split()
        cmd += [f"--uri={url}"]
        if public_key:
            cmd += [f"--public-keys={public_key.model_dump_json()}"]
        logger.info(f"kr-create [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert (
            process.returncode == 0
        ), f"otdfctl kas-registry create failed: {err.decode() if err else out.decode()}"
        return KasEntry.model_validate_json(out)

    def kas_registry_create_if_not_present(
        self, uri: str, key: PublicKey | None = None
    ) -> KasEntry:
        for e in self.kas_registry_list():
            if e.uri == uri:
                return e
        return self.kas_registry_create(uri, key)

    def kas_registry_keys_list(self, kas: KasEntry) -> list[KasKey]:
        cmd = self.otdfctl + "policy kas-registry key list".split()
        cmd += [f"--kas={kas.uri}"]
        logger.info(f"kr-keys-ls [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
            return []
        if out:
            print(out)
        assert process.returncode == 0
        o = json.loads(out)
        if not o:
            return []
        if isinstance(o, dict):
            o = o.get("kas_keys", [])
        return [KasKey(**n) for n in o]

    def kas_registry_create_public_key_only(
        self, kas: KasEntry, public_key: KasPublicKey
    ) -> KasKey:
        for k in self.kas_registry_keys_list(kas):
            if k.key.key_id == public_key.kid and k.kas_uri == kas.uri:
                return k

        if not public_key.algStr:
            public_key.algStr = kas_public_key_alg_to_str(public_key.alg)

        cmd = self.otdfctl + "policy kas-registry key create --mode public_key".split()
        cmd += [
            f"--kas={kas.uri}",
            f"--public-key-pem={base64.b64encode(public_key.pem.encode('utf-8')).decode('utf-8')}",
            f"--key-id={public_key.kid}",
            f"--algorithm={public_key.algStr}",
        ]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        logger.debug(f"Raw output from kas_registry_create_public_key_only: {out}")
        assert process.returncode == 0
        return KasKey.model_validate_json(out)

    def kas_registry_create_key(
        self,
        kas: KasEntry | str,
        key_id: str,
        mode: str | None = None,
        algorithm: str | None = None,
        public_key_pem: str | None = None,
        private_key_pem: str | None = None,
        provider_config_id: str | None = None,
        wrapping_key: str | None = None,
        wrapping_key_id: str | None = None,
    ) -> KasKey:
        """Create a KAS key with flexible options.

        Parameters
        - kas: KAS registry entry or URI/ID/Name string
        - key_id: desired key identifier
        - mode: one of public_key | provider | remote | local
        - algorithm: enum value or string like 'rsa:2048', 'ec:secp256r1'
        - labels: optional metadata as dict or list of 'k=v' strings
        - public_key_pem: PEM (raw or base64-encoded) for public key
        - private_key_pem: PEM (raw or base64-encoded) for private key
        - provider_config_id: config id for provider/remote modes
        - wrapping_key: AES key (hex) used to wrap generated private key (local mode)
        - wrapping_key_id: id for the wrapping key (semantics mode-dependent)
        """

        kas_id = kas.uri if isinstance(kas, KasEntry) else kas
        cmd = self.otdfctl + "policy kas-registry key create".split()
        cmd += [f"--kas={kas_id}", f"--key-id={key_id}"]

        if algorithm:
            cmd += [f"--algorithm={algorithm}"]
        if mode:
            cmd += [f"--mode={mode}"]

        if public_key_pem:
            encoded_pem = self._b64_pem(public_key_pem)
            cmd += [f"--public-key-pem={encoded_pem}"]
        if private_key_pem:
            encoded_pem = self._b64_pem(private_key_pem)
            cmd += [f"--private-key-pem={encoded_pem}"]

        if provider_config_id:
            cmd += [f"--provider-config-id={provider_config_id}"]
        if wrapping_key:
            cmd += [f"--wrapping-key={wrapping_key}"]
        if wrapping_key_id:
            cmd += [f"--wrapping-key-id={wrapping_key_id}"]

        logger.info(f"kas-registry key-create [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0
        return KasKey.model_validate_json(out)

    def kas_registry_import_key(
        self,
        kas: KasEntry | str,
        private_pem: str,
        public_pem: str,
        key_id: str,
        legacy: bool | None,
        wrapping_key: str,
        wrapping_key_id: str,
        algorithm: str,
    ):
        kas_id = kas.uri if isinstance(kas, KasEntry) else kas
        cmd = self.otdfctl + "policy kas-registry key import".split()
        cmd += [f"--kas={kas_id}", f"--key-id={key_id}"]
        cmd += [f"--algorithm={algorithm}"]
        cmd += [f"--public-key-pem={self._b64_pem(public_pem)}"]
        cmd += [f"--private-key-pem={self._b64_pem(private_pem)}"]
        cmd += [f"--wrapping-key={wrapping_key}"]
        cmd += [f"--wrapping-key-id={wrapping_key_id}"]

        if legacy:
            cmd += [f"--legacy={legacy}"]

        logger.info(f"kas-registry key-import [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0
        return KasKey.model_validate_json(out)

    def set_base_key(self, key: KasKey | str, kas: KasEntry | str):
        kas_id = kas.uri if isinstance(kas, KasEntry) else kas
        key_id = key.key.key_id if isinstance(key, KasKey) else key
        cmd = self.otdfctl + "policy kas-registry key base set".split()
        cmd += f"--key={key_id} --kas={kas_id}"
        logger.info(f"kas-registry base key set [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0
        return KasKey.model_validate_json(out)

    def key_assign_ns(self, key: KasKey, ns: Namespace) -> NamespaceKey:
        cmd = self.otdfctl + "policy attributes namespace key assign".split()
        cmd += [
            f"--key-id={key.key.id}",
            f"--namespace={ns.id}",
        ]
        logger.info(f"key-assign [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0
        return NamespaceKey.model_validate_json(out)

    # Deprecated
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

    def key_assign_attr(self, key: KasKey, attr: Attribute) -> AttributeKey:
        cmd = self.otdfctl + "policy attributes key assign".split()
        cmd += [
            f"--key-id={key.key.id}",
            f"--attribute={attr.id}",
        ]
        logger.info(f"key-assign [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0
        return AttributeKey.model_validate_json(out)

    # Deprecated
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

    def key_assign_value(self, key: KasKey, val: AttributeValue) -> ValueKey:
        cmd = self.otdfctl + "policy attributes value key assign".split()
        cmd += [
            f"--key-id={key.key.id}",
            f"--value={val.id}",
        ]
        logger.info(f"key-assign [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0
        return ValueKey.model_validate_json(out)

    # Deprecated
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

    def key_unassign_ns(self, key: KasKey, ns: Namespace) -> NamespaceKey:
        cmd = self.otdfctl + "policy attributes namespace key unassign".split()
        cmd += [
            f"--key-id={key.key.id}",
            f"--namespace={ns.id}",
        ]
        logger.info(f"key-assign [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        code = process.wait()
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert code == 0
        return NamespaceKey.model_validate_json(out)

    # Deprecated in otdfctl 0.22
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

    def key_unassign_attr(self, key: KasKey, attr: Attribute) -> AttributeKey:
        cmd = self.otdfctl + "policy attributes key unassign".split()
        cmd += [
            f"--key-id={key.key.id}",
            f"--attribute={attr.id}",
        ]
        logger.info(f"key-assign [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0
        return AttributeKey.model_validate_json(out)

    # Deprecated
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

    def key_unassign_value(self, key: KasKey, val: AttributeValue) -> ValueKey:
        cmd = self.otdfctl + "policy attributes value key unassign".split()
        cmd += [
            f"--key-id={key.key.id}",
            f"--value={val.id}",
        ]
        logger.info(f"key-assign [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0
        return ValueKey.model_validate_json(out)

    # Deprecated
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
            print(err, file=sys.stderr, flush=code != 0)
        if out:
            print(out, flush=code != 0)
        assert code == 0
        o = json.loads(out)
        if not o:
            return []
        if isinstance(o, dict):
            o = o.get("namespaces", [])

        return [Namespace(**n) for n in o]

    def namespace_create(self, name: str) -> Namespace:
        cmd = self.otdfctl + "policy attributes namespaces create".split()
        cmd += [f"--name={name}"]
        logger.info(f"ns-create [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        code = process.wait()
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr, flush=code != 0)
        if out:
            print(out, flush=code != 0)
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
            print(err, file=sys.stderr, flush=code != 0)
        if out:
            print(out, flush=code != 0)
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
            print(err, file=sys.stderr, flush=code != 0)
        if out:
            print(out, flush=code != 0)
        assert code == 0
        return SubjectConditionSet.model_validate_json(out)

    def scs_map(
        self,
        sc: str | SubjectConditionSet,
        value: str | AttributeValue,
        action: str | Action = "read",
    ) -> SubjectMapping:
        cmd: list[str] = self.otdfctl + "policy subject-mappings create".split()

        if self.flag_scs_map_action_standard:
            cmd += [
                f"--action-standard={action if isinstance(action, str) else action.name}"
            ]
        else:
            cmd += [f"--action={action if isinstance(action, str) else action.name}"]

        cmd += [
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
        if (
            code != 0
            and not self.flag_scs_map_action_standard
            and err.find(b"--action-standard") >= 0
        ):
            self.flag_scs_map_action_standard = True
            return self.scs_map(sc, value)

        assert code == 0
        return SubjectMapping.model_validate_json(out)

    def obligation_def_create(
        self, name: str, namespace: str | Namespace, value: list[str] | None
    ) -> Obligation:
        cmd = self.otdfctl + "policy obligations create".split()
        cmd += [
            f"--name={name}",
            f"--namespace={namespace.id if isinstance(namespace, Namespace) else namespace}",
        ]
        if value:
            cmd += [f"--value={','.join(value)}"]
        logger.info(f"obligation-def-create [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        code = process.wait()
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr, flush=code != 0)
        if out:
            print(out, flush=code != 0)
        assert code == 0
        return Obligation.model_validate_json(out)

    def obligation_value_create(
        self,
        obligation: str | Obligation,
        value: str,
        triggers: list[ObligationTrigger] | None = None,
    ) -> ObligationValue:
        """
        Create an obligation value with optional triggers.
        If you provide triggers with request context, the context needs to be in the form
        of an individual object and not a list of request contexts.
        """
        cmd = self.otdfctl + "policy obligations value create".split()
        cmd += [
            f"--obligation={obligation.id if isinstance(obligation, Obligation) else obligation}",
            f"--value={value}",
        ]
        if triggers:
            cmd += [f"--triggers=[{','.join([t.model_dump_json() for t in triggers])}]"]
        logger.info(f"obligation-value-create [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        code = process.wait()
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr, flush=code != 0)
        if out:
            print(out, flush=code != 0)
        assert code == 0
        return ObligationValue.model_validate_json(out)

    def obligation_triggers_create(
        self,
        obligation_value: str | ObligationValue,
        action: str | Action,
        attribute_value: str | AttributeValue,
        client_id: str | None = None,
    ) -> ObligationTrigger:
        cmd = self.otdfctl + "policy obligations triggers create".split()
        cmd += [
            f"--obligation-value={obligation_value.id if isinstance(obligation_value, ObligationValue) else obligation_value}",
            f"--action={action.id if isinstance(action, Action) else action}",
            f"--attribute-value={attribute_value.id if isinstance(attribute_value, AttributeValue) else attribute_value}",
        ]
        if client_id:
            cmd += [f"--client-id={client_id}"]
        logger.info(f"obligation-triggers-create [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        code = process.wait()
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr, flush=code != 0)
        if out:
            print(out, flush=code != 0)
        assert code == 0
        return ObligationTrigger.model_validate_json(out)
