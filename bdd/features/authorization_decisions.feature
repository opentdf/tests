@req:BR-301
Feature: Authorization Decisions via GetDecisions API
  As a platform integrator using OpenTDF
  I want to make authorization decisions without encryption/decryption
  So that I can implement authorization-only scenarios using OIDC authentication

  Background:
    Given the authorization service is available
    And I have valid OIDC authentication credentials
    And the platform is configured for authorization-only operations

  @cap:auth_type=oidc @cap:kas_type=none @cap:operation_mode=standalone @cap:policy=none @testrail:C101
  Scenario: Basic authorization decision for single entity
    Given I have an entity "bob@example.org" with email address
    And I have a resource with attributes:
      | attribute_fqn                              | value        |
      | https://example.com/attr/classification    | secret       |
      | https://example.com/attr/department        | engineering  |
    When I request authorization decision for "TRANSMIT" action
    Then the authorization decision should be "PERMIT" or "DENY"
    And the response should include the entity chain ID
    And evidence should be collected for the authorization request

  @cap:auth_type=oidc @cap:kas_type=none @cap:operation_mode=standalone @cap:policy=none @testrail:C102
  Scenario: Multiple entity authorization decisions
    Given I have multiple entities:
      | entity_id | entity_type   | value              |
      | ec1       | email_address | bob@example.org    |
      | ec2       | user_name     | alice@example.org  |
    And I have a resource with attributes:
      | attribute_fqn                              | value        |
      | https://example.com/attr/classification    | public       |
    When I request authorization decisions for "TRANSMIT" action
    Then I should receive decisions for both entities
    And each response should map to the correct entity chain ID
    And evidence should be collected for all authorization requests

  @cap:auth_type=oidc @cap:kas_type=none @cap:operation_mode=standalone @cap:policy=none @testrail:C103
  Scenario: Authorization for different action types
    Given I have an entity "alice@example.org" with email address
    And I have a resource with attributes:
      | attribute_fqn                              | value        |
      | https://example.com/attr/classification    | confidential |
    When I request authorization decision for "DECRYPT" action
    Then I should receive an authorization decision
    When I request authorization decision for "TRANSMIT" action  
    Then I should receive an authorization decision
    And the decisions may differ based on the action type
    And evidence should be collected for each authorization request

  @cap:auth_type=oidc @cap:kas_type=none @cap:operation_mode=standalone @cap:policy=none @testrail:C104
  Scenario: Resource attribute matching in authorization
    Given I have an entity "bob@example.org" with email address
    And I have multiple resource attributes:
      | attribute_fqn                              | value        |
      | https://example.com/attr/classification    | secret       |
      | https://example.com/attr/project           | apollo       |
      | https://example.com/attr/clearance         | top-secret   |
    When I request authorization decision for "TRANSMIT" action
    Then the authorization service should evaluate all resource attributes
    And the decision should be based on the entity's entitlements
    And evidence should be collected including all resource attributes

  @cap:auth_type=oidc @cap:kas_type=none @cap:operation_mode=standalone @cap:policy=none @testrail:C105
  Scenario: OIDC token validation in authorization
    Given I have a valid OIDC token for "alice@example.org"
    And I have a resource with attributes:
      | attribute_fqn                              | value        |
      | https://example.com/attr/department        | engineering  |
    When I make an authorization request using the OIDC token
    Then the authorization service should validate the token
    And the decision should be based on the token's claims
    And evidence should be collected including token validation

  @cap:auth_type=oidc @cap:kas_type=none @cap:operation_mode=standalone @cap:policy=none @testrail:C106 @error-handling
  Scenario: Invalid authorization request handling
    Given I have malformed request data
    When I attempt to make an authorization decision request
    Then the service should return an appropriate error response
    And the error should indicate the specific validation failure
    And evidence should be collected for the failed request

  @cap:auth_type=oidc @cap:kas_type=none @cap:operation_mode=standalone @cap:policy=none @testrail:C107 @error-handling
  Scenario: Missing entity information handling
    Given I have a request with empty entity chains
    And I have valid resource attributes
    When I request authorization decision for "TRANSMIT" action
    Then the service should return an error response
    And the error should indicate missing entity information
    And evidence should be collected for the invalid request

  @cap:auth_type=oidc @cap:kas_type=none @cap:operation_mode=standalone @cap:policy=none @testrail:C108 @performance
  Scenario: Bulk authorization decision performance
    Given I have 10 different entities with various attributes
    And I have multiple resources with different classifications
    When I request authorization decisions for all entity-resource combinations
    Then all decisions should be returned within 2 seconds
    And the response should maintain entity chain ID mappings
    And evidence should be collected for the bulk operation