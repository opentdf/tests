"""OpenTDF Command Line Tool wrapper for policy operations.

This module contains the OpentdfCommandLineTool class which provides a Python
interface to the otdfctl CLI tool for managing OpenTDF policies, attributes,
namespaces, KAS registries, and obligations.
"""

import base64
import json
import logging
import os
import subprocess
import sys

from abac import (
    Action,
    Attribute,
    AttributeKey,
    AttributeRule,
    AttributeValue,
    KasEntry,
    KasGrantAttribute,
    KasGrantNamespace,
    KasGrantValue,
    KasKey,
    KasPublicKey,
    Namespace,
    NamespaceKey,
    Obligation,
    ObligationTrigger,
    ObligationValue,
    PublicKey,
    SubjectConditionSet,
    SubjectMapping,
    SubjectSet,
    ValueKey,
    kas_public_key_alg_to_str,
)

logger = logging.getLogger("xtest")


class OpentdfCommandLineTool:
    # Flag to indicate we are using an older version of policy subject-mappings create that uses the `action-standard` flag
    # instead of just `action`
    flag_scs_map_action_standard: bool = False

    def __init__(self, otdfctl_path: str | None = None):
        path = otdfctl_path if otdfctl_path else "sdk/go/otdfctl.sh"
        if not os.path.isfile(path):
            raise FileNotFoundError(f"otdfctl.sh not found at path: {path}")
        self.otdfctl = [path]

    def _b64_pem(self, pem: str | None) -> str | None:
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
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0
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
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0, (
            f"otdfctl kas-registry create failed: {err.decode() if err else out.decode()}"
        )
        return KasEntry.model_validate_json(out)

    def _verify_kas_entry_keys(
        self, entry: KasEntry, expected_key: PublicKey | None
    ) -> None:
        """Assert that an existing KAS entry's public keys match expectations.

        Only performs verification if the entry has public_key field populated.
        This allows for entries registered without keys to be returned safely.
        """
        if expected_key is None:
            return
        if expected_key.cached is None:
            return
        # Only verify if entry actually has public keys registered
        if not entry.public_key or not entry.public_key.PublicKey or not entry.public_key.PublicKey.cached:
            logger.warning(
                f"KAS {entry.uri} has no public keys registered yet, "
                "skipping key verification (will be added later with kas_registry_create_public_key_only)"
            )
            return
        existing_pks = entry.public_key.PublicKey.cached.keys
        existing_by_kid = {k.kid: k for k in existing_pks}
        for expected in expected_key.cached.keys:
            found = existing_by_kid.get(expected.kid)
            assert found is not None, (
                f"KAS {entry.uri}: expected key kid={expected.kid} not present. "
                f"Existing kids: {list(existing_by_kid.keys())}"
            )
            assert found.pem.strip() == expected.pem.strip(), (
                f"KAS {entry.uri}: key kid={expected.kid} PEM mismatch"
            )

    def kas_registry_create_if_not_present(
        self, uri: str, key: PublicKey | None = None
    ) -> KasEntry:
        for e in self.kas_registry_list():
            if e.uri == uri:
                self._verify_kas_entry_keys(e, key)
                return e
        # Try to create; handle race where another worker created it first
        cmd = self.otdfctl + "policy kas-registry create".split()
        cmd += [f"--uri={uri}"]
        if key:
            cmd += [f"--public-keys={key.model_dump_json()}"]
        logger.info(f"kr-create-if-not-present [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        if process.returncode == 0:
            return KasEntry.model_validate_json(out)
        # Creation failed — check if it was a conflict
        err_str = (err.decode() if err else "") + (out.decode() if out else "")
        if "already_exists" in err_str or "unique field violation" in err_str:
            logger.info(
                f"KAS {uri} already exists (race condition), fetching existing entry"
            )
            for e in self.kas_registry_list():
                if e.uri == uri:
                    self._verify_kas_entry_keys(e, key)
                    return e
            raise AssertionError(
                f"KAS registry create for {uri} failed with 'already_exists' but "
                f"entry not found in subsequent list. Error: {err_str}"
            )
        raise AssertionError(
            f"otdfctl kas-registry create failed: {err_str}"
        )

    def kas_registry_keys_list(self, kas: KasEntry) -> list[KasKey]:
        cmd = self.otdfctl + "policy kas-registry key list".split()
        cmd += [f"--kas={kas.uri}"]
        logger.info(f"kr-keys-ls [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        if process.returncode != 0 and err.find(b"not found") >= 0:
            return []
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
        # Check if key already exists before attempting to create
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
        logger.info(f"kas-registry public-key-create [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        logger.debug(f"Raw output from kas_registry_create_public_key_only: {out}")

        # Handle race condition: if key already exists, verify it matches and return it
        if process.returncode != 0:
            err_str = (err.decode() if err else "") + (out.decode() if out else "")
            if "already_exists" in err_str or "unique field violation" in err_str:
                logger.info(
                    f"Key {public_key.kid} already exists on {kas.uri}, verifying it matches"
                )
                # Query existing keys and find the one we tried to create
                existing_keys = self.kas_registry_keys_list(kas)
                for existing_key in existing_keys:
                    if existing_key.key.key_id == public_key.kid:
                        # Key exists and matches what we tried to create
                        logger.info(
                            f"Key {public_key.kid} already exists with matching properties, returning it"
                        )
                        return existing_key
                # Key not found in list (shouldn't happen)
                raise AssertionError(
                    f"Key creation failed with 'already_exists' error, but key {public_key.kid} "
                    f"not found when querying existing keys. This suggests a conflict. "
                    f"Error: {err_str}"
                )
            # Different error, raise it
            assert False, f"Key creation failed: {err_str}"

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
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)

        # Handle race condition: if key already exists, return the existing one
        if process.returncode != 0:
            err_str = (err.decode() if err else "") + (out.decode() if out else "")
            if "already_exists" in err_str or "unique field violation" in err_str:
                logger.info(
                    f"Key {key_id} already exists on {kas_id} (race condition), fetching existing key"
                )
                kas_entry = kas if isinstance(kas, KasEntry) else None
                if kas_entry is None:
                    raise AssertionError(
                        f"Key creation failed with 'already_exists' error but cannot verify "
                        f"(kas was passed as string). Error: {err_str}"
                    )
                existing_keys = self.kas_registry_keys_list(kas_entry)
                for existing_key in existing_keys:
                    if existing_key.key.key_id == key_id:
                        logger.info(
                            f"Key {key_id} already exists with matching key_id, returning it"
                        )
                        return existing_key
                raise AssertionError(
                    f"Key creation failed with 'already_exists' error, but key {key_id} "
                    f"not found when querying existing keys. Error: {err_str}"
                )
            assert False, f"Key creation failed: {err_str}"

        return KasKey.model_validate_json(out)

    def kas_registry_import_key(
        self,
        kas: KasEntry | str,
        private_pem: str | None,
        public_pem: str,
        key_id: str,
        legacy: bool | None,
        wrapping_key: str,
        wrapping_key_id: str,
        algorithm: str,
    ):
        kas_entry = kas if isinstance(kas, KasEntry) else None
        kas_id = kas.uri if isinstance(kas, KasEntry) else kas
        cmd = self.otdfctl + "policy kas-registry key import".split()
        cmd += [f"--kas={kas_id}", f"--key-id={key_id}"]
        cmd += [f"--algorithm={algorithm}"]
        cmd += [f"--public-key-pem={self._b64_pem(public_pem)}"]
        if private_pem:
            cmd += [f"--private-key-pem={self._b64_pem(private_pem)}"]
        cmd += [f"--wrapping-key={wrapping_key}"]
        cmd += [f"--wrapping-key-id={wrapping_key_id}"]

        if legacy:
            cmd += [f"--legacy={legacy}"]

        logger.info(f"kas-registry key-import [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)

        # Handle race condition: if key already exists, verify it matches and return it
        if process.returncode != 0:
            err_str = (err.decode() if err else "") + (out.decode() if out else "")
            if "already_exists" in err_str or "unique field violation" in err_str:
                logger.info(
                    f"Key {key_id} already exists on {kas_id}, verifying it matches"
                )
                # Query existing keys and find the one we tried to import
                if kas_entry is None:
                    # Can't query without KasEntry object, re-raise
                    raise AssertionError(
                        f"Key import failed with 'already_exists' error but cannot verify "
                        f"(kas was passed as string). Error: {err_str}"
                    )
                existing_keys = self.kas_registry_keys_list(kas_entry)
                for existing_key in existing_keys:
                    if existing_key.key.key_id == key_id:
                        # Key exists and matches what we tried to import
                        logger.info(
                            f"Key {key_id} already exists with matching properties, returning it"
                        )
                        return existing_key
                # Key not found in list (shouldn't happen)
                raise AssertionError(
                    f"Key import failed with 'already_exists' error, but key {key_id} "
                    f"not found when querying existing keys. This suggests a conflict. "
                    f"Error: {err_str}"
                )
            # Different error, raise it
            assert False, f"Key import failed: {err_str}"

        return KasKey.model_validate_json(out)

    def set_base_key(self, key: KasKey | str, kas: KasEntry | str):
        kas_id = kas.uri if isinstance(kas, KasEntry) else kas
        key_id = key.key.key_id if isinstance(key, KasKey) else key
        cmd = self.otdfctl + "policy kas-registry key base set".split()
        cmd += [f"--key={key_id}", f"--kas={kas_id}"]
        logger.info(f"kas-registry base key set [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0

    def key_assign_ns(self, key: KasKey, ns: Namespace) -> NamespaceKey:
        cmd = self.otdfctl + "policy attributes namespace key assign".split()
        cmd += [
            f"--key-id={key.key.id}",
            f"--namespace={ns.id}",
        ]
        logger.info(f"key-assign [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0
        return KasGrantNamespace.model_validate_json(out)

    def key_assign_attr(self, key: KasKey, attr: Attribute) -> AttributeKey:
        cmd = self.otdfctl + "policy attributes key assign".split()
        cmd += [
            f"--key-id={key.key.id}",
            f"--attribute={attr.id}",
        ]
        logger.info(f"key-assign [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0
        return KasGrantAttribute.model_validate_json(out)

    def key_assign_value(self, key: KasKey, val: AttributeValue) -> ValueKey:
        cmd = self.otdfctl + "policy attributes value key assign".split()
        cmd += [
            f"--key-id={key.key.id}",
            f"--value={val.id}",
        ]
        logger.info(f"key-assign [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0
        return KasGrantValue.model_validate_json(out)

    def key_unassign_ns(self, key: KasKey, ns: Namespace) -> NamespaceKey:
        cmd = self.otdfctl + "policy attributes namespace key unassign".split()
        cmd += [
            f"--key-id={key.key.id}",
            f"--namespace={ns.id}",
        ]
        logger.info(f"key-assign [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0
        return NamespaceKey.model_validate_json(out)

    # Deprecated in otdfctl 0.22
    def grant_unassign_ns(self, kas: KasEntry, ns: Namespace) -> KasGrantNamespace:
        cmd = self.otdfctl + "policy kas-grants unassign".split()
        cmd += [
            f"--kas-id={kas.id}",
            f"--namespace-id={ns.id}",
        ]
        logger.info(f"grant-update [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0
        return KasGrantNamespace.model_validate_json(out)

    def key_unassign_attr(self, key: KasKey, attr: Attribute) -> AttributeKey:
        cmd = self.otdfctl + "policy attributes key unassign".split()
        cmd += [
            f"--key-id={key.key.id}",
            f"--attribute={attr.id}",
        ]
        logger.info(f"key-assign [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0
        return KasGrantAttribute.model_validate_json(out)

    def key_unassign_value(self, key: KasKey, val: AttributeValue) -> ValueKey:
        cmd = self.otdfctl + "policy attributes value key unassign".split()
        cmd += [
            f"--key-id={key.key.id}",
            f"--value={val.id}",
        ]
        logger.info(f"key-assign [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        assert process.returncode == 0
        return KasGrantValue.model_validate_json(out)

    def namespace_list(self) -> list[Namespace]:
        cmd = self.otdfctl + "policy attributes namespaces list".split()
        logger.info(f"ns-ls [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr, flush=process.returncode != 0)
        if out:
            print(out, flush=process.returncode != 0)
        assert process.returncode == 0
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
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr, flush=process.returncode != 0)
        if out:
            print(out, flush=process.returncode != 0)
        assert process.returncode == 0
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
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr, flush=process.returncode != 0)
        if out:
            print(out, flush=process.returncode != 0)
        assert process.returncode == 0
        return Attribute.model_validate_json(out)

    def scs_create(self, scs: list[SubjectSet]) -> SubjectConditionSet:
        cmd = self.otdfctl + "policy subject-condition-sets create".split()

        cmd += [f"--subject-sets=[{','.join([s.model_dump_json() for s in scs])}]"]

        logger.info(f"scs-create [{' '.join(cmd)}]")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr, flush=process.returncode != 0)
        if out:
            print(out, flush=process.returncode != 0)
        assert process.returncode == 0
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
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr)
        if out:
            print(out)
        if (
            process.returncode != 0
            and not self.flag_scs_map_action_standard
            and err.find(b"--action-standard") >= 0
        ):
            self.flag_scs_map_action_standard = True
            return self.scs_map(sc, value)

        assert process.returncode == 0
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
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr, flush=process.returncode != 0)
        if out:
            print(out, flush=process.returncode != 0)
        assert process.returncode == 0
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
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr, flush=process.returncode != 0)
        if out:
            print(out, flush=process.returncode != 0)
        assert process.returncode == 0
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
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if err:
            print(err, file=sys.stderr, flush=process.returncode != 0)
        if out:
            print(out, flush=process.returncode != 0)
        assert process.returncode == 0
        return ObligationTrigger.model_validate_json(out)
