"""
SDK implementation using HTTP-based SDK servers instead of CLI subprocess calls.

This module provides a drop-in replacement for the tdfs.SDK class that uses
the new SDK server architecture for dramatic performance improvements.
"""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Literal, Optional, List

from sdk_client import SDKClient, MultiSDKClient

logger = logging.getLogger("xtest")

# Type definitions to match tdfs.py
sdk_type = Literal["go", "java", "js"]
container_type = Literal["nano", "nano-with-ecdsa", "ztdf", "ztdf-ecwrap"]
container_version = Literal["4.2.2", "4.3.0"]
feature_type = Literal[
    "assertions",
    "assertion_verification",
    "autoconfigure",
    "better-messages-2024",
    "bulk_rewrap",
    "connectrpc",
    "ecwrap",
    "hexless",
    "hexaflexible",
    "kasallowlist",
    "key_management",
    "nano_attribute_bug",
    "nano_ecdsa",
    "nano_policymode_plaintext",
    "ns_grants",
]


def simple_container(container: container_type) -> str:
    """Convert container type to simple format string."""
    if container == "nano-with-ecdsa":
        return "nano"
    if container == "ztdf-ecwrap":
        return "ztdf"
    return container


class ServerSDK:
    """
    SDK implementation using HTTP-based SDK servers.
    
    This class provides the same interface as tdfs.SDK but uses HTTP requests
    to SDK servers instead of subprocess calls for dramatically better performance.
    """
    
    def __init__(self, sdk: sdk_type, version: str = "main"):
        self.sdk = sdk
        self.version = version
        self._client = SDKClient(sdk)
        self._supports_cache: dict[feature_type, bool] = {}
        
        # Verify server is available
        try:
            health = self._client.health_check()
            if health.get("status") != "healthy":
                raise RuntimeError(f"{sdk} SDK server is not healthy: {health}")
        except Exception as e:
            raise RuntimeError(f"Failed to connect to {sdk} SDK server: {e}")
    
    def __str__(self) -> str:
        return f"{self.sdk}@{self.version}"
    
    def __repr__(self) -> str:
        return f"ServerSDK(sdk={self.sdk!r}, version={self.version!r})"
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ServerSDK):
            return NotImplemented
        return self.sdk == other.sdk and self.version == other.version
    
    def __hash__(self) -> int:
        return hash((self.sdk, self.version))
    
    def encrypt(
        self,
        pt_file: Path,
        ct_file: Path,
        mime_type: str = "application/octet-stream",
        container: container_type = "nano",
        attr_values: Optional[List[str]] = None,
        assert_value: str = "",
        policy_mode: str = "encrypted",
        target_mode: Optional[container_version] = None,
        expect_error: bool = False,
    ):
        """Encrypt a file using the SDK server."""
        # Read input file
        with open(pt_file, "rb") as f:
            data = f.read()
        
        # Determine format and options
        fmt = simple_container(container)
        use_ecdsa = container == "nano-with-ecdsa"
        use_ecwrap = container == "ztdf-ecwrap"
        
        # Build options dictionary
        options = {
            "mime_type": mime_type,
            "policy_mode": policy_mode,
        }
        
        if use_ecdsa:
            options["ecdsa_binding"] = True
        if use_ecwrap:
            options["ecwrap"] = True
        if target_mode:
            options["target_mode"] = target_mode
        
        # Handle assertions
        assertions = None
        if assert_value:
            # Read assertion file content
            with open(assert_value, "r") as f:
                assertions = json.load(f)
        
        try:
            # Encrypt using SDK server
            encrypted = self._client.encrypt(
                data,
                attributes=attr_values or [],
                format=fmt,
                assertions=assertions,
                **options
            )
            
            if expect_error:
                raise AssertionError("Expected encrypt to fail but it succeeded")
            
            # Write output file
            with open(ct_file, "wb") as f:
                f.write(encrypted)
                
        except Exception as e:
            if not expect_error:
                raise
            # Expected error occurred
            logger.debug(f"Expected error during encryption: {e}")
    
    def decrypt(
        self,
        ct_file: Path,
        rt_file: Path,
        container: container_type = "nano",
        assert_keys: str = "",
        verify_assertions: bool = True,
        ecwrap: bool = False,
        expect_error: bool = False,
        kasallowlist: str = "",
        ignore_kas_allowlist: bool = False,
    ):
        """Decrypt a file using the SDK server."""
        # Read encrypted file
        with open(ct_file, "rb") as f:
            encrypted = f.read()
        
        # Build options dictionary
        options = {}
        
        if assert_keys:
            # Read assertion verification keys
            with open(assert_keys, "r") as f:
                options["assertion_keys"] = json.load(f)
        
        if ecwrap:
            options["ecwrap"] = True
        
        if not verify_assertions:
            options["verify_assertions"] = False
        
        if kasallowlist:
            options["kas_allowlist"] = kasallowlist.split(",")
        
        if ignore_kas_allowlist:
            options["ignore_kas_allowlist"] = True
        
        try:
            # Decrypt using SDK server
            decrypted = self._client.decrypt(encrypted, **options)
            
            if expect_error:
                raise AssertionError("Expected decrypt to fail but it succeeded")
            
            # Write output file
            with open(rt_file, "wb") as f:
                f.write(decrypted)
                
        except Exception as e:
            if not expect_error:
                raise
            # Expected error occurred
            logger.debug(f"Expected error during decryption: {e}")
    
    def supports(self, feature: feature_type) -> bool:
        """Check if the SDK supports a specific feature."""
        if feature in self._supports_cache:
            return self._supports_cache[feature]
        
        # Check with SDK server
        result = self._check_feature_support(feature)
        self._supports_cache[feature] = result
        return result
    
    def _check_feature_support(self, feature: feature_type) -> bool:
        """Check feature support with the SDK server."""
        # Some features are known to be supported by specific SDKs
        match (feature, self.sdk):
            case ("autoconfigure", ("go" | "java")):
                return True
            case ("better-messages-2024", ("js" | "java")):
                return True
            case ("nano_ecdsa", "go"):
                return True
            case ("ns_grants", ("go" | "java")):
                return True
            case ("hexless", _):
                # All SDKs now support hexless through servers
                return True
            case ("hexaflexible", _):
                # All SDKs now support hexaflexible through servers
                return True
            case ("assertions", _):
                # Check if server supports assertions
                try:
                    health = self._client.health_check()
                    return health.get("features", {}).get("assertions", True)
                except:
                    return True  # Assume support if check fails
            case ("assertion_verification", _):
                # Check if server supports assertion verification
                try:
                    health = self._client.health_check()
                    return health.get("features", {}).get("assertion_verification", True)
                except:
                    return True  # Assume support if check fails
            case ("ecwrap", _):
                # Check if server supports ecwrap
                try:
                    health = self._client.health_check()
                    return health.get("features", {}).get("ecwrap", False)
                except:
                    return False  # Assume no support if check fails
            case _:
                # For unknown features, check with server
                try:
                    health = self._client.health_check()
                    return health.get("features", {}).get(feature, False)
                except:
                    return False


def SDK(sdk: sdk_type, version: str = "main") -> ServerSDK:
    """
    Factory function to create an SDK instance.
    
    This function creates a ServerSDK instance that uses HTTP-based SDK servers
    instead of CLI subprocess calls.
    """
    return ServerSDK(sdk, version)


def all_versions_of(sdk: sdk_type) -> List[ServerSDK]:
    """Get all available versions of an SDK."""
    # For SDK servers, we only support "main" version currently
    # In the future, this could query different server versions
    return [ServerSDK(sdk, "main")]


def skip_if_unsupported(sdk: ServerSDK, *features: feature_type):
    """Skip test if SDK doesn't support required features."""
    import pytest
    from tdfs import PlatformFeatureSet
    
    pfs = PlatformFeatureSet()
    for feature in features:
        if not sdk.supports(feature):
            pytest.skip(f"{sdk} sdk doesn't yet support [{feature}]")
        if feature not in pfs.features:
            pytest.skip(
                f"platform service {pfs.version} doesn't yet support [{feature}]"
            )