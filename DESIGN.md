# Test Framework Modernization - High-Level Design

## Executive Summary

This document provides the high-level technical design for the OpenTDF Test Framework Modernization. It details the
architecture, key components, and guiding principles for the test framework, focusing on creating a fast, reliable, and
maintainable testing platform.

## 1. Architecture Overview

### 1.1 High-Level Architecture

The framework is designed with a layered architecture to separate concerns and improve modularity.

```mermaid
graph TB
    subgraph "Test Orchestration Layer"
        TD[Test Discovery Engine]
        TE[Test Executor]
        RE[Result Engine]
    end
    
    subgraph "Test Suites"
        XT[XTest Suite<br/>pytest]
        BDD[BDD Suite<br/>pytest-bdd]
        PERF[Performance Tests]
        VUL[Vulnerability Tests<br/>Playwright]
    end
    
    subgraph "Service Layer"
        SL[Service Locator]
        AM[Artifact Manager]
        EM[Evidence Manager]
    end
    
    subgraph "Integration Layer"
        TR[TestRail Client]
        JI[Jira Client]
        GH[GitHub Actions]
    end
    
    subgraph "Infrastructure"
        PS[Platform Services<br/>KAS/Policy]
        KC[Keycloak]
        PG[PostgreSQL]
        S3[Artifact Storage]
    end
    
    TD --> TE
    TE --> XT
    TE --> BDD
    TE --> PERF
    TE --> VUL
    
    XT --> SL
    BDD --> SL
    
    TE --> AM
    AM --> EM
    EM --> S3
    
    RE --> TR
    RE --> JI
    RE --> GH
    
    SL --> PS
    SL --> KC
    SL --> PG
```

### 1.2 Component Interactions

The test framework operates in distinct phases:

1. **Discovery Phase**: Identifies tests to run based on tags, profiles, and impact analysis.
2. **Execution Phase**: Runs tests with controlled parallelization and deterministic behavior.
3. **Collection Phase**: Gathers artifacts, evidence, and results.
4. **Publishing Phase**: Sends results to external systems (TestRail, Jira).
5. **Reporting Phase**: Generates coverage matrices and dashboards.

## 2. Core Components

### 2.1 Test Discovery Engine

A planned component responsible for discovering tests based on tags, profiles, and impact analysis. This will allow for
intelligent test selection and prioritization.

### 2.2 Service Locator

Resolves service endpoints and credentials at runtime, decoupling tests from the underlying environment and eliminating
hardcoded configuration.

### 2.3 Evidence Manager

Manages the collection and storage of test evidence, including logs, screenshots, and other artifacts. It ensures that
every test run produces a complete and auditable record.

### 2.4 TestRail Integration

A client for integrating with TestRail, allowing for automatic creation of test runs and publishing of test results.

### 2.5 Profile Management

The framework is driven by test profiles, which define the capabilities, configurations, and policies for a given test
run. This allows for flexible and powerful test configuration without code changes.

## 3. Key Design Principles

### 3.1 Unified Test Execution

All test suites, including `xtest` and `bdd`, are executed through `pytest`. This provides a single, unified test
runner, which simplifies test execution and enables consistent parallelization and reporting across all test types.

### 3.2 Determinism

The framework is designed to be deterministic, with built-in controllers for time and randomness. This minimizes test
flakiness and ensures that tests are reproducible.

### 3.3 Performance

A key focus of the modernization is performance. The new architecture uses persistent HTTP servers for each SDK, which
dramatically reduces test execution time by eliminating the overhead of subprocess creation and connection setup for
each test operation.

### 3.4 Security

Security is a primary concern. The framework is designed to avoid storing secrets in code or artifacts, and all service
credentials are resolved at runtime from a secure source.

## 4. Implementation Plan

### Phase 1A: Foundation (Weeks 1-3)

1. Implement core framework components
2. Set up profile system and capability catalog
3. Create Service Locator and time/randomness controllers
4. Establish artifact storage structure

### Phase 1B: Integration (Weeks 4-6)

5. Integrate with existing xtest suite
6. Add BDD support with pytest-bdd
7. Implement TestRail client
8. Add optional Jira integration

### Phase 1C: Validation (Weeks 7-9)

9. Create linters and validators
10. Implement evidence collection
11. Build coverage matrix generator
12. Set up CI/CD pipeline

### Phase 1D: Stabilization (Weeks 10-12)

13. Performance optimization for <10min execution
14. Flake detection and elimination
15. Documentation and training
16. Acceptance testing and rollout

## 5. Key Enhancements

- **Test Framework Unification**: The BDD suite has been fully migrated from `behave` to `pytest-bdd` to enable unified
  test execution.
- **Single Test Runner**: All tests (`xtest` and `bdd`) are now run through `pytest`.
- **Parallel Execution**: Both `xtest` and `bdd` suites run in parallel using `pytest-xdist`.
- **Unified Configuration**: All test configuration is centralized in `pyproject.toml`.
- **SDK Server Architecture**: A new architecture using persistent HTTP servers for each SDK has been implemented,
  resulting in a 10x+ performance improvement.
