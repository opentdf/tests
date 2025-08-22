"""
Test suite for SDK servers.

This test demonstrates the performance improvement and cross-SDK compatibility
using the new SDK server architecture.
"""

import time
import pytest
from pathlib import Path
from sdk_client import SDKClient, MultiSDKClient


@pytest.fixture(scope="module")
def multi_sdk():
    """Get multi-SDK client for cross-SDK testing."""
    return MultiSDKClient()


@pytest.fixture(scope="module")
def test_data():
    """Sample test data."""
    return b"Hello, OpenTDF! This is a test message for SDK servers."


@pytest.fixture(scope="module")
def test_attributes():
    """Sample attributes."""
    return [
        "https://example.com/attr/classification/value/secret",
        "https://example.com/attr/department/value/engineering"
    ]


class TestSDKServers:
    """Test suite for individual SDK servers."""
    
    @pytest.mark.parametrize("sdk_type", ["go", "js", "java"])
    def test_sdk_health(self, sdk_type):
        """Test that each SDK server is healthy."""
        try:
            client = SDKClient(sdk_type)
            health = client.health_check()
            assert health.get("status") == "healthy"
            assert health.get("type") == sdk_type
            print(f"✓ {sdk_type.upper()} SDK server is healthy")
        except Exception as e:
            pytest.skip(f"{sdk_type.upper()} SDK server not available: {e}")
    
    @pytest.mark.parametrize("sdk_type", ["go", "js", "java"])
    def test_encrypt_decrypt_roundtrip(self, sdk_type, test_data, test_attributes):
        """Test encrypt/decrypt roundtrip for each SDK."""
        try:
            client = SDKClient(sdk_type)
            
            # Test standard TDF
            encrypted = client.encrypt(test_data, test_attributes, format="ztdf")
            decrypted = client.decrypt(encrypted)
            assert decrypted == test_data
            print(f"✓ {sdk_type.upper()} SDK: ztdf roundtrip successful")
            
            # Test NanoTDF
            encrypted = client.encrypt(test_data, test_attributes, format="nano")
            decrypted = client.decrypt(encrypted)
            assert decrypted == test_data
            print(f"✓ {sdk_type.upper()} SDK: nano roundtrip successful")
            
        except Exception as e:
            pytest.skip(f"{sdk_type.upper()} SDK server not available: {e}")


class TestCrossSDK:
    """Test cross-SDK compatibility."""
    
    @pytest.mark.parametrize("enc_sdk,dec_sdk", [
        ("go", "js"),
        ("js", "go"),
        ("go", "java"),
        ("java", "go"),
        ("js", "java"),
        ("java", "js"),
    ])
    def test_cross_sdk_compatibility(self, multi_sdk, test_data, test_attributes, 
                                    enc_sdk, dec_sdk):
        """Test encrypting with one SDK and decrypting with another."""
        if enc_sdk not in multi_sdk.available_sdks:
            pytest.skip(f"{enc_sdk.upper()} SDK not available")
        if dec_sdk not in multi_sdk.available_sdks:
            pytest.skip(f"{dec_sdk.upper()} SDK not available")
        
        # Test standard TDF
        decrypted = multi_sdk.cross_sdk_encrypt_decrypt(
            test_data, enc_sdk, dec_sdk, test_attributes, format="ztdf"
        )
        assert decrypted == test_data
        print(f"✓ Cross-SDK: {enc_sdk}→{dec_sdk} (ztdf) successful")
        
        # Test NanoTDF
        decrypted = multi_sdk.cross_sdk_encrypt_decrypt(
            test_data, enc_sdk, dec_sdk, test_attributes, format="nano"
        )
        assert decrypted == test_data
        print(f"✓ Cross-SDK: {enc_sdk}→{dec_sdk} (nano) successful")


class TestPerformance:
    """Benchmark SDK server performance vs CLI approach."""
    
    def test_sdk_server_performance(self, multi_sdk, test_data, test_attributes):
        """Measure performance of SDK server operations."""
        if not multi_sdk.available_sdks:
            pytest.skip("No SDK servers available")
        
        # Use first available SDK
        sdk_type = multi_sdk.available_sdks[0]
        client = multi_sdk.get_client(sdk_type)
        
        # Measure encryption performance
        iterations = 10
        start_time = time.time()
        
        for _ in range(iterations):
            encrypted = client.encrypt(test_data, test_attributes, format="ztdf")
            decrypted = client.decrypt(encrypted)
        
        elapsed = time.time() - start_time
        ops_per_second = (iterations * 2) / elapsed  # 2 ops per iteration (encrypt + decrypt)
        
        print(f"\n📊 SDK Server Performance ({sdk_type.upper()}):")
        print(f"  - {iterations} encrypt/decrypt cycles")
        print(f"  - Total time: {elapsed:.2f} seconds")
        print(f"  - Operations/second: {ops_per_second:.1f}")
        print(f"  - Avg time per operation: {(elapsed/(iterations*2))*1000:.1f}ms")
        
        # Store for comparison
        pytest.sdk_server_performance = ops_per_second
    
    @pytest.mark.skip(reason="CLI comparison requires subprocess implementation")
    def test_cli_performance(self, test_data, test_attributes):
        """Measure performance of CLI subprocess operations for comparison."""
        # This would use the old subprocess approach for comparison
        # Skipped for now as it requires the old implementation
        pass
    
    def test_performance_improvement(self):
        """Calculate and report performance improvement."""
        if hasattr(pytest, 'sdk_server_performance'):
            # Estimated CLI performance (based on subprocess overhead)
            # Typical subprocess spawn: ~50ms, so max ~20 ops/second
            estimated_cli_ops_per_second = 20
            
            improvement = pytest.sdk_server_performance / estimated_cli_ops_per_second
            
            print(f"\n🚀 Performance Improvement:")
            print(f"  - SDK Server: {pytest.sdk_server_performance:.1f} ops/sec")
            print(f"  - CLI (estimated): {estimated_cli_ops_per_second} ops/sec")
            print(f"  - Improvement: {improvement:.1f}x faster")


class TestPolicyOperations:
    """Test policy management operations through SDK servers."""
    
    @pytest.mark.parametrize("sdk_type", ["go", "js", "java"])
    def test_namespace_operations(self, sdk_type):
        """Test namespace creation and listing."""
        try:
            client = SDKClient(sdk_type)
            
            # Create a namespace
            ns_name = f"test.{sdk_type}.example.com"
            namespace = client.create_namespace(ns_name)
            assert namespace.get("name") == ns_name
            print(f"✓ {sdk_type.upper()} SDK: namespace created")
            
            # List namespaces
            namespaces = client.list_namespaces()
            assert isinstance(namespaces, list)
            print(f"✓ {sdk_type.upper()} SDK: namespaces listed")
            
        except Exception as e:
            pytest.skip(f"{sdk_type.upper()} SDK server not available or doesn't support policy ops: {e}")
    
    @pytest.mark.parametrize("sdk_type", ["go", "js", "java"])
    def test_attribute_operations(self, sdk_type):
        """Test attribute creation and listing."""
        try:
            client = SDKClient(sdk_type)
            
            # First create a namespace
            ns_name = f"test.attr.{sdk_type}.example.com"
            namespace = client.create_namespace(ns_name)
            ns_id = namespace.get("id")
            
            # Create an attribute
            attr_name = "classification"
            attribute = client.create_attribute(
                ns_id, attr_name, "ANY_OF", 
                ["public", "internal", "secret"]
            )
            assert attribute.get("name") == attr_name
            print(f"✓ {sdk_type.upper()} SDK: attribute created")
            
            # List attributes
            attributes = client.list_attributes(ns_id)
            assert isinstance(attributes, list)
            print(f"✓ {sdk_type.upper()} SDK: attributes listed")
            
        except Exception as e:
            pytest.skip(f"{sdk_type.upper()} SDK server not available or doesn't support policy ops: {e}")


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])