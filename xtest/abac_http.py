"""HTTP client implementation for test helper server.

This module provides an HTTP-based alternative to the subprocess-based
OpentdfCommandLineTool, dramatically improving test performance by eliminating
process creation overhead.
"""

import json
import logging
import os
from typing import Optional, List
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from abac import (
    KasEntry, Namespace, Attribute, AttributeRule, AttributeValue,
    SubjectConditionSet, SubjectMapping, SubjectSet,
    KasKey, KasPublicKey, PublicKey,
    NamespaceKey, AttributeKey, ValueKey,
    KasGrantNamespace, KasGrantAttribute, KasGrantValue,
    kas_public_key_alg_to_str
)

logger = logging.getLogger("xtest")


class OpentdfHttpClient:
    """HTTP client for test helper server operations."""
    
    def __init__(self, base_url: Optional[str] = None):
        """Initialize the HTTP client.
        
        Args:
            base_url: Base URL of the test helper server.
                     Defaults to TESTHELPER_URL env var or http://localhost:8090
        """
        if base_url:
            self.base_url = base_url
        else:
            self.base_url = os.environ.get("TESTHELPER_URL", "http://localhost:8090")
        
        # Create session with connection pooling and retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.3,
            status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default timeout
        self.timeout = 30
    
    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make an HTTP request to the test helper server.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments for requests
        
        Returns:
            Response JSON as dict
            
        Raises:
            AssertionError: If the request fails
        """
        url = f"{self.base_url}/api/{endpoint}"
        
        # Set default timeout if not provided
        if "timeout" not in kwargs:
            kwargs["timeout"] = self.timeout
        
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json() if response.text else {}
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP request failed: {method} {url} - {e}")
            raise AssertionError(f"HTTP request failed: {e}")
    
    # KAS Registry operations
    
    def kas_registry_list(self) -> List[KasEntry]:
        """List all KAS registry entries."""
        logger.info("kr-ls [HTTP]")
        result = self._request("GET", "kas-registry/list")
        if not result:
            return []
        return [KasEntry(**entry) for entry in result]
    
    def kas_registry_create(self, url: str, public_key: Optional[PublicKey] = None) -> KasEntry:
        """Create a new KAS registry entry."""
        data = {"uri": url}
        if public_key:
            data["public_keys"] = public_key.model_dump_json()
        
        logger.info(f"kr-create [HTTP] {url}")
        result = self._request("POST", "kas-registry/create", json=data)
        return KasEntry.model_validate(result)
    
    def kas_registry_create_if_not_present(self, uri: str, key: Optional[PublicKey] = None) -> KasEntry:
        """Create KAS registry entry if it doesn't exist."""
        for entry in self.kas_registry_list():
            if entry.uri == uri:
                return entry
        return self.kas_registry_create(uri, key)
    
    def kas_registry_keys_list(self, kas: KasEntry) -> List[KasKey]:
        """List keys for a KAS registry entry."""
        logger.info(f"kr-keys-ls [HTTP] {kas.uri}")
        result = self._request("GET", "kas-registry/keys/list", params={"kas": kas.uri})
        if not result:
            return []
        return [KasKey(**key) for key in result]
    
    def kas_registry_create_public_key_only(self, kas: KasEntry, public_key: KasPublicKey) -> KasKey:
        """Create a public key for a KAS registry entry."""
        # Check if key already exists
        for key in self.kas_registry_keys_list(kas):
            if key.key.key_id == public_key.kid and key.kas_uri == kas.uri:
                return key
        
        if not public_key.algStr:
            public_key.algStr = kas_public_key_alg_to_str(public_key.alg)
        
        import base64
        data = {
            "kas_uri": kas.uri,
            "public_key_pem": base64.b64encode(public_key.pem.encode('utf-8')).decode('utf-8'),
            "key_id": public_key.kid,
            "algorithm": public_key.algStr
        }
        
        logger.info(f"kr-key-create [HTTP] {kas.uri} {public_key.kid}")
        result = self._request("POST", "kas-registry/keys/create", json=data)
        return KasKey.model_validate(result)
    
    # Namespace operations
    
    def namespace_list(self) -> List[Namespace]:
        """List all namespaces."""
        logger.info("ns-ls [HTTP]")
        result = self._request("GET", "namespaces/list")
        if not result:
            return []
        return [Namespace(**ns) for ns in result]
    
    def namespace_create(self, name: str) -> Namespace:
        """Create a new namespace."""
        logger.info(f"ns-create [HTTP] {name}")
        result = self._request("POST", "namespaces/create", json={"name": name})
        return Namespace.model_validate(result)
    
    # Attribute operations
    
    def attribute_create(
        self, 
        namespace: str | Namespace, 
        name: str, 
        t: AttributeRule, 
        values: List[str]
    ) -> Attribute:
        """Create a new attribute."""
        namespace_id = namespace if isinstance(namespace, str) else namespace.id
        
        data = {
            "namespace_id": namespace_id,
            "name": name,
            "rule": t.name,
            "values": values if values else []
        }
        
        logger.info(f"attr-create [HTTP] {namespace_id}/{name}")
        result = self._request("POST", "attributes/create", json=data)
        return Attribute.model_validate(result)
    
    # Key assignment operations
    
    def key_assign_ns(self, key: KasKey, ns: Namespace) -> NamespaceKey:
        """Assign a key to a namespace."""
        data = {
            "key_id": key.key.id,
            "namespace_id": ns.id
        }
        logger.info(f"key-assign-ns [HTTP] {key.key.id} -> {ns.id}")
        result = self._request("POST", "attributes/namespace/key/assign", json=data)
        return NamespaceKey.model_validate(result)
    
    def key_assign_attr(self, key: KasKey, attr: Attribute) -> AttributeKey:
        """Assign a key to an attribute."""
        data = {
            "key_id": key.key.id,
            "attribute_id": attr.id
        }
        logger.info(f"key-assign-attr [HTTP] {key.key.id} -> {attr.id}")
        result = self._request("POST", "attributes/key/assign", json=data)
        return AttributeKey.model_validate(result)
    
    def key_assign_value(self, key: KasKey, val: AttributeValue) -> ValueKey:
        """Assign a key to an attribute value."""
        data = {
            "key_id": key.key.id,
            "value_id": val.id
        }
        logger.info(f"key-assign-value [HTTP] {key.key.id} -> {val.id}")
        result = self._request("POST", "attributes/value/key/assign", json=data)
        return ValueKey.model_validate(result)
    
    def key_unassign_ns(self, key: KasKey, ns: Namespace) -> NamespaceKey:
        """Unassign a key from a namespace."""
        data = {
            "key_id": key.key.id,
            "namespace_id": ns.id
        }
        logger.info(f"key-unassign-ns [HTTP] {key.key.id} -> {ns.id}")
        result = self._request("POST", "attributes/namespace/key/unassign", json=data)
        return NamespaceKey.model_validate(result)
    
    def key_unassign_attr(self, key: KasKey, attr: Attribute) -> AttributeKey:
        """Unassign a key from an attribute."""
        data = {
            "key_id": key.key.id,
            "attribute_id": attr.id
        }
        logger.info(f"key-unassign-attr [HTTP] {key.key.id} -> {attr.id}")
        result = self._request("POST", "attributes/key/unassign", json=data)
        return AttributeKey.model_validate(result)
    
    def key_unassign_value(self, key: KasKey, val: AttributeValue) -> ValueKey:
        """Unassign a key from an attribute value."""
        data = {
            "key_id": key.key.id,
            "value_id": val.id
        }
        logger.info(f"key-unassign-value [HTTP] {key.key.id} -> {val.id}")
        result = self._request("POST", "attributes/value/key/unassign", json=data)
        return ValueKey.model_validate(result)
    
    # Deprecated grant operations (for backward compatibility)
    
    def grant_assign_ns(self, kas: KasEntry, ns: Namespace) -> KasGrantNamespace:
        """Deprecated: Assign KAS grant to namespace."""
        logger.warning("grant_assign_ns is deprecated, use key_assign_ns")
        # For now, return a mock response
        return KasGrantNamespace(namespace_id=ns.id, key_access_server_id=kas.id)
    
    def grant_assign_attr(self, kas: KasEntry, attr: Attribute) -> KasGrantAttribute:
        """Deprecated: Assign KAS grant to attribute."""
        logger.warning("grant_assign_attr is deprecated, use key_assign_attr")
        return KasGrantAttribute(attribute_id=attr.id, key_access_server_id=kas.id)
    
    def grant_assign_value(self, kas: KasEntry, val: AttributeValue) -> KasGrantValue:
        """Deprecated: Assign KAS grant to value."""
        logger.warning("grant_assign_value is deprecated, use key_assign_value")
        return KasGrantValue(value_id=val.id, key_access_server_id=kas.id)
    
    def grant_unassign_ns(self, kas: KasEntry, ns: Namespace) -> KasGrantNamespace:
        """Deprecated: Unassign KAS grant from namespace."""
        logger.warning("grant_unassign_ns is deprecated, use key_unassign_ns")
        return KasGrantNamespace(namespace_id=ns.id, key_access_server_id=kas.id)
    
    def grant_unassign_attr(self, kas: KasEntry, attr: Attribute) -> KasGrantAttribute:
        """Deprecated: Unassign KAS grant from attribute."""
        logger.warning("grant_unassign_attr is deprecated, use key_unassign_attr")
        return KasGrantAttribute(attribute_id=attr.id, key_access_server_id=kas.id)
    
    def grant_unassign_value(self, kas: KasEntry, val: AttributeValue) -> KasGrantValue:
        """Deprecated: Unassign KAS grant from value."""
        logger.warning("grant_unassign_value is deprecated, use key_unassign_value")
        return KasGrantValue(value_id=val.id, key_access_server_id=kas.id)
    
    # Subject Condition Set operations
    
    def scs_create(self, scs: List[SubjectSet]) -> SubjectConditionSet:
        """Create a subject condition set."""
        subject_sets_json = "[" + ",".join([s.model_dump_json() for s in scs]) + "]"
        data = {"subject_sets": subject_sets_json}
        
        logger.info(f"scs-create [HTTP]")
        result = self._request("POST", "subject-condition-sets/create", json=data)
        return SubjectConditionSet.model_validate(result)
    
    def scs_map(self, sc: str | SubjectConditionSet, value: str | AttributeValue) -> SubjectMapping:
        """Create a subject mapping."""
        sc_id = sc if isinstance(sc, str) else sc.id
        value_id = value if isinstance(value, str) else value.id
        
        data = {
            "attribute_value_id": value_id,
            "subject_condition_set_id": sc_id,
            "action": "read"
        }
        
        logger.info(f"sm-create [HTTP] {sc_id} -> {value_id}")
        result = self._request("POST", "subject-mappings/create", json=data)
        return SubjectMapping.model_validate(result)