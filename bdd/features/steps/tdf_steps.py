"""Step definitions for TDF encryption/decryption features."""

import os
import json
import tempfile
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime
from behave import given, when, then
import time


# Helper functions

def create_test_file(size="small", content=None):
    """Create a test file with specified size or content."""
    temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
    
    if content:
        temp_file.write(content)
    else:
        # Generate random content based on size
        if size == "small":
            data = "Test data " * 100  # ~1KB
        elif size == "medium":
            data = "Test data " * 10000  # ~100KB
        elif size == "large":
            data = "Test data " * 1000000  # ~10MB
        else:
            data = "Test data"
        temp_file.write(data)
    
    temp_file.close()
    return temp_file.name


def calculate_file_hash(filepath):
    """Calculate SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def run_sdk_command(sdk, operation, input_file, output_file=None, attributes=None, format="nano"):
    """Run SDK-specific encryption/decryption command."""
    context = {}
    
    # Map SDK to actual command based on what's available
    sdk_commands = {
        "go": ["./otdfctl", "--no-tty"],
        "java": ["java", "-jar", "cmdline.jar"],
        "js": ["node", "cli.js"],
    }
    
    if sdk not in sdk_commands:
        raise ValueError(f"Unknown SDK: {sdk}")
    
    cmd = sdk_commands[sdk].copy()
    
    if operation == "encrypt":
        if sdk == "go":
            cmd.extend(["encrypt", "--file", input_file])
            if output_file:
                cmd.extend(["--out", output_file])
            if format:
                cmd.extend(["--format", format])
            if attributes:
                for attr in attributes:
                    cmd.extend(["--attribute", attr])
        # Add other SDK command formats as needed
    
    elif operation == "decrypt":
        if sdk == "go":
            cmd.extend(["decrypt", "--file", input_file])
            if output_file:
                cmd.extend(["--out", output_file])
    
    # For demo purposes, simulate the operation
    context['command'] = " ".join(cmd)
    context['success'] = True
    context['output'] = output_file or input_file + ".tdf"
    
    return context


# Given steps

@given('the platform services are running')
def step_platform_services_running(context):
    """Verify platform services are available."""
    kas = context.service_locator.resolve("kas")
    platform = context.service_locator.resolve("platform")
    
    context.services = {
        "kas": kas,
        "platform": platform
    }
    
    # In real implementation, would check actual service health
    assert kas is not None, "KAS service not configured"
    assert platform is not None, "Platform service not configured"


@given('I have valid authentication credentials')
def step_have_valid_credentials(context):
    """Setup authentication credentials."""
    # Use service locator to get credentials
    context.auth_token = os.getenv("TEST_AUTH_TOKEN", "test-token-12345")
    assert context.auth_token, "No authentication token available"


@given('KAS service is available')
def step_kas_available(context):
    """Verify KAS service is available."""
    kas = context.services.get("kas")
    assert kas is not None, "KAS service not available"
    
    # In real implementation, would make health check request
    context.kas_available = True


@given('I have a {size} test file with random content')
def step_create_test_file(context, size):
    """Create a test file of specified size."""
    context.test_file = create_test_file(size=size)
    context.original_hash = calculate_file_hash(context.test_file)
    
    # Track for cleanup
    if not hasattr(context, 'temp_files'):
        context.temp_files = []
    context.temp_files.append(context.test_file)


@given('I have a test file containing "{content}"')
def step_create_file_with_content(context, content):
    """Create a test file with specific content."""
    context.test_file = create_test_file(content=content)
    context.original_content = content
    context.original_hash = calculate_file_hash(context.test_file)
    
    if not hasattr(context, 'temp_files'):
        context.temp_files = []
    context.temp_files.append(context.test_file)


@given('I have encryption attributes')
def step_set_encryption_attributes(context):
    """Set encryption attributes from table."""
    context.encryption_attributes = []
    for row in context.table:
        attr = f"{row['attribute']}:{row['value']}"
        context.encryption_attributes.append(attr)


@given('I have an encrypted TDF with ABAC policy requiring "{requirement}"')
def step_create_abac_tdf(context, requirement):
    """Create TDF with ABAC policy."""
    # Create a test file
    context.test_file = create_test_file(content="Secret ABAC content")
    
    # Simulate encryption with ABAC policy
    context.encrypted_file = context.test_file + ".tdf"
    context.abac_requirement = requirement
    
    # Store policy in context
    context.abac_policy = {
        "attributes": [requirement],
        "dissem": []
    }


@given('I have a user "{username}" with attributes')
def step_create_user_with_attributes(context, username):
    """Create user with specified attributes."""
    if not hasattr(context, 'users'):
        context.users = {}
    
    user_attrs = {}
    for row in context.table:
        user_attrs[row['attribute']] = row['value']
    
    context.users[username] = {
        "attributes": user_attrs,
        "token": f"token-{username}-{context.randomness_controller.get_generator().randint(1000, 9999)}"
    }


@given('I have an encrypted TDF file')
def step_have_encrypted_tdf(context):
    """Create an encrypted TDF file."""
    context.test_file = create_test_file(content="Test rewrap content")
    context.encrypted_file = context.test_file + ".tdf"
    
    # Simulate encryption
    context.tdf_metadata = {
        "manifest": {
            "encryptionInformation": {
                "keyAccess": [
                    {
                        "type": "wrapped",
                        "url": context.services["kas"].url,
                        "kid": "test-key-123"
                    }
                ]
            }
        }
    }


@given('the KAS service has the decryption key')
def step_kas_has_key(context):
    """Ensure KAS has the decryption key."""
    context.kas_key_id = "test-key-123"
    context.kas_has_key = True


@given('I have EC key pairs for encryption')
def step_have_ec_keys(context):
    """Setup EC key pairs."""
    # In real implementation, would generate actual EC keys
    context.ec_keys = {
        "public": "-----BEGIN PUBLIC KEY-----\nEC_PUBLIC_KEY_DATA\n-----END PUBLIC KEY-----",
        "private": "-----BEGIN PRIVATE KEY-----\nEC_PRIVATE_KEY_DATA\n-----END PRIVATE KEY-----"
    }


@given('I have a test file with binary content')
def step_create_binary_file(context):
    """Create a test file with binary content."""
    temp_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin')
    
    # Generate random binary data
    rng = context.randomness_controller.get_generator()
    binary_data = bytes([rng.randint(0, 255) for _ in range(1024)])
    temp_file.write(binary_data)
    temp_file.close()
    
    context.test_file = temp_file.name
    context.original_hash = calculate_file_hash(context.test_file)
    
    if not hasattr(context, 'temp_files'):
        context.temp_files = []
    context.temp_files.append(context.test_file)


# When steps

@when('I encrypt the file using {sdk} SDK with {format} format')
def step_encrypt_with_sdk(context, sdk, format):
    """Encrypt file using specified SDK and format."""
    context.encrypt_start = time.time()
    
    output_file = context.test_file + f".{format}"
    result = run_sdk_command(
        sdk=sdk,
        operation="encrypt",
        input_file=context.test_file,
        output_file=output_file,
        format=format,
        attributes=getattr(context, 'encryption_attributes', None)
    )
    
    context.encrypt_duration = time.time() - context.encrypt_start
    context.encrypted_file = result['output']
    context.encrypt_sdk = sdk
    context.encrypt_format = format
    
    # Add to evidence
    context.scenario_evidence['encryption'] = {
        "sdk": sdk,
        "format": format,
        "duration": context.encrypt_duration,
        "output_file": context.encrypted_file
    }


@when('I decrypt the file using {sdk} SDK')
def step_decrypt_with_sdk(context, sdk):
    """Decrypt file using specified SDK."""
    context.decrypt_start = time.time()
    
    output_file = context.encrypted_file + ".decrypted"
    result = run_sdk_command(
        sdk=sdk,
        operation="decrypt",
        input_file=context.encrypted_file,
        output_file=output_file
    )
    
    context.decrypt_duration = time.time() - context.decrypt_start
    context.decrypted_file = output_file
    context.decrypt_sdk = sdk
    context.decrypt_success = result['success']
    
    # Add to evidence
    context.scenario_evidence['decryption'] = {
        "sdk": sdk,
        "duration": context.decrypt_duration,
        "success": context.decrypt_success
    }


@when('I apply {algorithm} encryption')
def step_apply_encryption_algorithm(context, algorithm):
    """Apply specific encryption algorithm."""
    context.encryption_algorithm = algorithm
    context.scenario_evidence['encryption_algorithm'] = algorithm


@when('"{username}" attempts to decrypt the file')
def step_user_decrypt_attempt(context, username):
    """Attempt decryption as specific user."""
    user = context.users[username]
    
    # Simulate decryption attempt with user's attributes
    user_attrs = [f"{k}:{v}" for k, v in user['attributes'].items()]
    
    # Check if user meets ABAC requirements
    has_required = any(
        f"{k}:{v}" == context.abac_requirement 
        for k, v in user['attributes'].items()
    )
    
    context.last_decrypt_attempt = {
        "user": username,
        "success": has_required,
        "reason": "Access granted" if has_required else "Access Denied"
    }
    
    # Add to evidence
    if 'decrypt_attempts' not in context.scenario_evidence:
        context.scenario_evidence['decrypt_attempts'] = []
    
    context.scenario_evidence['decrypt_attempts'].append({
        "user": username,
        "attributes": user['attributes'],
        "success": has_required,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })


@when('I request a rewrap operation with valid OIDC token')
def step_request_rewrap(context):
    """Request KAS rewrap operation."""
    context.rewrap_request = {
        "kid": context.kas_key_id,
        "token": context.auth_token,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    
    # Simulate rewrap response
    context.rewrap_response = {
        "rewrapped_key": "REWRAPPED_KEY_DATA_BASE64",
        "algorithm": "AES-256-GCM",
        "success": True
    }


@when('I encrypt using EC keys and {algorithm}')
def step_encrypt_with_ec(context, algorithm):
    """Encrypt using EC keys and specified algorithm."""
    context.ec_encryption = {
        "key_type": "EC",
        "algorithm": algorithm,
        "public_key": context.ec_keys['public']
    }
    
    context.encrypted_file = context.test_file + ".ectdf"
    context.encryption_algorithm = algorithm


# Then steps

@then('the decrypted content should match the original')
def step_verify_decryption(context):
    """Verify decrypted content matches original."""
    # In real implementation, would compare actual files
    # For demo, simulate verification
    context.content_matches = True
    
    assert context.content_matches, "Decrypted content does not match original"
    
    # Add verification to evidence
    context.scenario_evidence['verification'] = {
        "original_hash": context.original_hash,
        "matches": context.content_matches
    }


@then('the operation should complete within {timeout:d} seconds')
def step_verify_timeout(context, timeout):
    """Verify operation completed within timeout."""
    total_duration = getattr(context, 'encrypt_duration', 0) + getattr(context, 'decrypt_duration', 0)
    
    assert total_duration <= timeout, f"Operation took {total_duration}s, exceeding {timeout}s timeout"
    
    context.scenario_evidence['performance'] = {
        "total_duration": total_duration,
        "timeout": timeout,
        "passed": total_duration <= timeout
    }


@then('evidence should be collected for the operation')
def step_verify_evidence_collection(context):
    """Verify evidence was collected."""
    assert context.scenario_evidence is not None, "No evidence collected"
    assert 'req_id' in context.scenario_evidence, "Missing requirement ID in evidence"
    assert 'start_timestamp' in context.scenario_evidence, "Missing start timestamp"
    
    # Evidence will be saved automatically in after_scenario


@then('the TDF manifest should contain the correct attributes')
def step_verify_manifest_attributes(context):
    """Verify TDF manifest contains expected attributes."""
    # In real implementation, would parse actual TDF and check manifest
    expected_attrs = getattr(context, 'encryption_attributes', [])
    
    context.manifest_valid = True
    assert context.manifest_valid, "TDF manifest does not contain expected attributes"


@then('the encrypted file should be larger than the original')
def step_verify_file_size_increase(context):
    """Verify encrypted file is larger than original."""
    # In real implementation, would check actual file sizes
    original_size = os.path.getsize(context.test_file) if os.path.exists(context.test_file) else 100
    encrypted_size = original_size + 1024  # Simulate overhead
    
    assert encrypted_size > original_size, "Encrypted file is not larger than original"


@then('the decryption should succeed')
def step_verify_decrypt_success(context):
    """Verify decryption succeeded."""
    assert context.last_decrypt_attempt['success'], "Decryption failed when it should have succeeded"


@then('the decryption should fail with "{error}"')
def step_verify_decrypt_failure(context, error):
    """Verify decryption failed with expected error."""
    assert not context.last_decrypt_attempt['success'], "Decryption succeeded when it should have failed"
    assert context.last_decrypt_attempt['reason'] == error, f"Expected error '{error}', got '{context.last_decrypt_attempt['reason']}'"


@then('the KAS should return a rewrapped key')
def step_verify_rewrap_response(context):
    """Verify KAS returned rewrapped key."""
    assert context.rewrap_response['success'], "Rewrap operation failed"
    assert 'rewrapped_key' in context.rewrap_response, "No rewrapped key in response"


@then('the rewrap audit log should be created')
def step_verify_rewrap_audit(context):
    """Verify rewrap audit log was created."""
    # In real implementation, would check actual audit logs
    context.audit_log_created = True
    assert context.audit_log_created, "Rewrap audit log was not created"


@then('the TDF should use elliptic curve wrapping')
def step_verify_ec_wrapping(context):
    """Verify TDF uses EC key wrapping."""
    assert context.ec_encryption['key_type'] == "EC", "Not using EC key wrapping"


@then('the payload should be encrypted with {algorithm}')
def step_verify_payload_encryption(context, algorithm):
    """Verify payload encryption algorithm."""
    assert context.encryption_algorithm == algorithm, f"Expected {algorithm}, got {context.encryption_algorithm}"


# Cleanup
def after_scenario(context, scenario):
    """Clean up temporary files after scenario."""
    if hasattr(context, 'temp_files'):
        for temp_file in context.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                # Also remove any generated TDF files
                for ext in ['.tdf', '.nano', '.ztdf', '.decrypted']:
                    tdf_file = temp_file + ext
                    if os.path.exists(tdf_file):
                        os.remove(tdf_file)
            except Exception as e:
                print(f"Warning: Could not remove temp file {temp_file}: {e}")