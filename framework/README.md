# Test Framework

This directory contains the core components of the test framework modernization project. The framework is designed to be a modular, extensible, and maintainable system for testing the OpenTDF platform.

## Architecture

The framework is designed with a layered architecture, as described in the [DESIGN.md](../../DESIGN.md) document. The key layers are:

*   **Test Orchestration Layer**: Responsible for discovering, executing, and reporting test results.
*   **Test Suites**: The actual test suites, such as `xtest` and `bdd`.
*   **Service Layer**: Provides common services to the test suites, such as service location and artifact management.
*   **Integration Layer**: Provides integrations with external systems, such as TestRail and Jira.

## Core Components

The `framework` directory is organized into the following subdirectories:

*   `core/`: Contains the core components of the framework:
    *   `models.py`: Pydantic models for the framework's data structures.
    *   `profiles.py`: The `ProfileManager` for handling profile-based testing.
    *   `service_locator.py`: The `ServiceLocator` for dynamic service resolution.
*   `integrations/`: Contains integrations with external systems, such as TestRail.
*   `linters/`: Contains custom linters for enforcing test standards.
*   `reporting/`: Contains tools for generating test reports, such as the coverage matrix.
*   `schemas/`: Contains JSON schemas for validating data structures, such as the evidence JSON.
*   `utils/`: Contains utility modules, such as the `TimeController` and `RandomnessController` for deterministic testing.

## Key Features

The framework provides the following key features:

*   **Profile-Based Testing**: Allows for running different sets of tests with different configurations by using profiles.
*   **Evidence Collection**: Automatically collects evidence for each test run, including logs, screenshots, and other artifacts.
*   **Deterministic Testing**: Provides tools for controlling time and randomness to ensure that tests are reproducible.
*   **Service Discovery**: The `ServiceLocator` provides a way to dynamically resolve the endpoints of the platform services.
*   **Extensibility**: The framework is designed to be easily extensible with new test suites, services, and integrations.

For more information, please refer to the [DESIGN.md](../../DESIGN.md) and [REQUIREMENTS.md](../../REQUIREMENTS.md) documents.
