@req:BR-101
Feature: Framework Integration Demo
  As a test framework developer
  I want to verify the framework components work correctly
  So that I can ensure the test infrastructure is reliable

  @smoke @cap:framework=core
  Scenario: Service Locator resolves services correctly
    Given the framework is initialized
    When I resolve the "kas" service
    Then the service should have a valid URL
    And the service endpoint should be "localhost"
    And evidence should be collected for the operation

  @cap:framework=determinism
  Scenario: Time Controller provides deterministic time
    Given the framework is initialized
    And the time controller is active
    When I advance time by 2 hours
    Then the controlled time should be 2 hours ahead
    And evidence should be collected for the operation

  @cap:framework=determinism
  Scenario: Randomness Controller provides deterministic values
    Given the framework is initialized
    And the randomness controller is active with seed 42
    When I generate 5 random numbers
    Then the sequence should be deterministic
    And evidence should be collected for the operation

  @cap:framework=profiles
  Scenario Outline: Profile Manager loads profiles correctly
    Given the framework is initialized
    And a profile "<profile>" exists
    When I load the profile
    Then the profile should have valid capabilities
    And the profile should have configuration
    And evidence should be collected for the operation

    Examples:
      | profile           |
      | cross-sdk-basic   |