@req:BR-101 @req:BR-302
Feature: TDF Encryption and Decryption
  As a developer using OpenTDF
  I want to encrypt and decrypt data across different SDKs
  So that I can ensure cross-SDK compatibility

  Background:
    Given the platform services are running
    And I have valid authentication credentials
    And KAS service is available

  @smoke @cap:format=nano @testrail:C001
  Scenario Outline: Cross-SDK Nano TDF encryption and decryption
    Given I have a <size> test file with random content
    When I encrypt the file using <encrypt_sdk> SDK with nano format
    And I decrypt the file using <decrypt_sdk> SDK
    Then the decrypted content should match the original
    And the operation should complete within <timeout> seconds
    And evidence should be collected for the operation

    Examples:
      | encrypt_sdk | decrypt_sdk | size  | timeout |
      | go          | go          | small | 5       |
      | go          | java        | small | 10      |
      | java        | go          | small | 10      |
      | js          | go          | small | 10      |

  @cap:format=ztdf @cap:encryption=aes256gcm @testrail:C002
  Scenario Outline: Standard TDF3 encryption with AES-256-GCM
    Given I have a test file containing "<content>"
    And I have encryption attributes:
      | attribute                | value    |
      | classification           | secret   |
      | department              | engineering |
    When I encrypt the file using <sdk> SDK with ztdf format
    And I apply AES-256-GCM encryption
    Then the TDF manifest should contain the correct attributes
    And the encrypted file should be larger than the original
    And evidence should be collected for the operation

    Examples:
      | sdk  | content                    |
      | go   | Hello, OpenTDF World!      |
      | java | Sensitive data content     |
      | js   | Test encryption payload    |

  @cap:policy=abac-basic @risk:high @testrail:C003
  Scenario: ABAC policy enforcement during decryption
    Given I have an encrypted TDF with ABAC policy requiring "clearance:secret"
    And I have a user "alice" with attributes:
      | attribute  | value      |
      | clearance  | secret     |
      | group      | engineering |
    And I have a user "bob" with attributes:
      | attribute  | value      |
      | clearance  | public     |
      | group      | marketing  |
    When "alice" attempts to decrypt the file
    Then the decryption should succeed
    When "bob" attempts to decrypt the file
    Then the decryption should fail with "Access Denied"
    And evidence should be collected for both operations

  @cap:kas_type=standard @cap:auth_type=oidc @testrail:C004
  Scenario: KAS key rewrap operation
    Given I have an encrypted TDF file
    And the KAS service has the decryption key
    When I request a rewrap operation with valid OIDC token
    Then the KAS should return a rewrapped key
    And the rewrap audit log should be created
    And evidence should be collected for the operation

  @cap:format=ztdf-ecwrap @cap:encryption=chacha20poly1305 @testrail:C005
  Scenario: Elliptic curve encryption with ChaCha20-Poly1305
    Given I have EC key pairs for encryption
    And I have a test file with binary content
    When I encrypt using EC keys and ChaCha20-Poly1305
    Then the TDF should use elliptic curve wrapping
    And the payload should be encrypted with ChaCha20-Poly1305
    And evidence should be collected for the operation