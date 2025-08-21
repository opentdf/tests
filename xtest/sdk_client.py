"""
Universal SDK client for testing.

This client can communicate with any SDK server (Go, JS, Java)
to perform encrypt/decrypt operations and policy management.
Each SDK server runs on a different port and uses its native SDK.
"""

import json
import logging
import os
from typing import Optional, List, Dict, Any
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

logger = logging.getLogger("xtest")


class SDKClient:
    """Client for communicating with SDK test servers."""
    
    # Default ports for each SDK server
    SDK_PORTS = {
        'go': 8091,
        'java': 8092,
        'js': 8093,
    }
    
    def __init__(self, sdk_type: str, base_url: Optional[str] = None):
        """Initialize SDK client.
        
        Args:
            sdk_type: Type of SDK ('go', 'java', 'js')
            base_url: Optional base URL override
        """
        self.sdk_type = sdk_type
        
        if base_url:
            self.base_url = base_url
        else:
            port = os.environ.get(f'{sdk_type.upper()}_SDK_PORT', self.SDK_PORTS.get(sdk_type, 8091))
            self.base_url = f"http://localhost:{port}"
        
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
        """Make an HTTP request to the SDK server.
        
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
            logger.error(f"SDK request failed ({self.sdk_type}): {method} {url} - {e}")
            raise AssertionError(f"SDK request failed: {e}")
    
    def health_check(self) -> Dict[str, Any]:
        """Check if the SDK server is healthy."""
        try:
            response = self.session.get(f"{self.base_url}/healthz", timeout=2)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Health check failed for {self.sdk_type} SDK: {e}")
            return {"status": "unhealthy", "error": str(e)}
    
    # Encryption/Decryption operations
    
    def encrypt(self, data: bytes, attributes: List[str], format: str = "ztdf") -> bytes:
        """Encrypt data using the SDK.
        
        Args:
            data: Data to encrypt
            attributes: List of attribute FQNs
            format: TDF format ('nano' or 'ztdf')
        
        Returns:
            Encrypted TDF data
        """
        import base64
        
        logger.info(f"Encrypting with {self.sdk_type} SDK (format: {format})")
        
        result = self._request("POST", "encrypt", json={
            "data": base64.b64encode(data).decode('utf-8'),
            "attributes": attributes,
            "format": format
        })
        
        return base64.b64decode(result['encrypted'])
    
    def decrypt(self, tdf_data: bytes) -> bytes:
        """Decrypt TDF data using the SDK.
        
        Args:
            tdf_data: Encrypted TDF data
        
        Returns:
            Decrypted data
        """
        import base64
        
        logger.info(f"Decrypting with {self.sdk_type} SDK")
        
        result = self._request("POST", "decrypt", json={
            "data": base64.b64encode(tdf_data).decode('utf-8')
        })
        
        return base64.b64decode(result['decrypted'])
    
    # Policy management operations (if supported by SDK server)
    
    def list_namespaces(self) -> List[Dict[str, Any]]:
        """List all namespaces."""
        logger.info(f"Listing namespaces with {self.sdk_type} SDK")
        result = self._request("GET", "namespaces/list")
        return result if isinstance(result, list) else result.get('namespaces', [])
    
    def create_namespace(self, name: str) -> Dict[str, Any]:
        """Create a new namespace."""
        logger.info(f"Creating namespace '{name}' with {self.sdk_type} SDK")
        return self._request("POST", "namespaces/create", json={"name": name})
    
    def create_attribute(self, namespace_id: str, name: str, rule: str = "ANY_OF", 
                        values: Optional[List[str]] = None) -> Dict[str, Any]:
        """Create a new attribute."""
        logger.info(f"Creating attribute '{name}' with {self.sdk_type} SDK")
        return self._request("POST", "attributes/create", json={
            "namespace_id": namespace_id,
            "name": name,
            "rule": rule,
            "values": values or []
        })
    
    def list_attributes(self, namespace_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List attributes."""
        logger.info(f"Listing attributes with {self.sdk_type} SDK")
        params = {"namespace_id": namespace_id} if namespace_id else {}
        result = self._request("GET", "attributes/list", params=params)
        return result if isinstance(result, list) else result.get('attributes', [])


class MultiSDKClient:
    """Client that can work with multiple SDK servers for cross-SDK testing."""
    
    def __init__(self):
        """Initialize multi-SDK client."""
        self.clients = {}
        self.available_sdks = []
        
        # Try to connect to each SDK server
        for sdk_type in ['go', 'js', 'java']:
            try:
                client = SDKClient(sdk_type)
                health = client.health_check()
                if health.get('status') == 'healthy':
                    self.clients[sdk_type] = client
                    self.available_sdks.append(sdk_type)
                    logger.info(f"{sdk_type.upper()} SDK server is available")
                else:
                    logger.warning(f"{sdk_type.upper()} SDK server is not healthy: {health}")
            except Exception as e:
                logger.warning(f"Could not connect to {sdk_type.upper()} SDK server: {e}")
    
    def get_client(self, sdk_type: str) -> SDKClient:
        """Get a specific SDK client."""
        if sdk_type not in self.clients:
            raise ValueError(f"SDK '{sdk_type}' is not available. Available: {self.available_sdks}")
        return self.clients[sdk_type]
    
    def cross_sdk_encrypt_decrypt(self, data: bytes, encrypt_sdk: str, decrypt_sdk: str,
                                  attributes: List[str] = None, format: str = "ztdf") -> bytes:
        """Encrypt with one SDK and decrypt with another.
        
        Args:
            data: Data to encrypt
            encrypt_sdk: SDK to use for encryption
            decrypt_sdk: SDK to use for decryption
            attributes: Attributes to apply
            format: TDF format
        
        Returns:
            Decrypted data (should match original)
        """
        encrypt_client = self.get_client(encrypt_sdk)
        decrypt_client = self.get_client(decrypt_sdk)
        
        logger.info(f"Cross-SDK test: encrypt with {encrypt_sdk}, decrypt with {decrypt_sdk}")
        
        # Encrypt with first SDK
        encrypted = encrypt_client.encrypt(data, attributes or [], format)
        
        # Decrypt with second SDK
        decrypted = decrypt_client.decrypt(encrypted)
        
        return decrypted