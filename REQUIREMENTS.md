# Test Framework Modernization - Phase 1 Requirements

## Executive Summary

This document outlines the requirements for Phase 1 of the OpenTDF Test Framework Modernization initiative. The goal is to establish a stable, fast, and deterministic test execution pipeline with comprehensive artifact management, TestRail/Jira integration, and business requirement-driven testing.

## 1. Business Requirements

### In-Scope for Phase 1

| BR ID | Description | Priority | Current State |
|-------|-------------|----------|---------------|
| BR-101 | Core product test suite operational and reliable | P0 | Partially Met - xtest operational but lacks determinism |
| BR-102 | Dev/test environment reliable and quick to set up | P0 | Partially Met - Docker compose exists but setup is complex |
| BR-103 | Documentation for test procedures and tools | P1 | Not Met - Limited documentation exists |
| BR-301 | Feature Coverage Matrix | P1 | Not Met - No coverage reporting |
| BR-302 | Cross-product compatibility validation | P0 | Met - xtest validates cross-SDK compatibility |
| BR-303 | Consolidate key management test tools | P1 | Partially Met - Multiple KAS testing approaches |

### Out of Scope for Phase 1
- Performance benchmarking improvements
- Additional SDK support beyond current (Go, Java, JS, Swift)
- Migration of legacy tdf3-js tests
- Kubernetes-based test execution

## 2. Functional Requirements

### 2.1 Test Execution Pipeline

#### FR-101: Performance Targets
- **xtest suite**: Must complete in ≤10 minutes wall-clock time in CI/PR lane
- **BDD suite**: Must complete in ≤15 minutes wall-clock time in CI/PR lane
- **Parallel execution**: Support configurable parallelization levels

#### FR-102: Determinism
- Flake rate must be <0.5% per test run
- All time-based operations must use controlled/seeded time sources
- Random values must be seeded and reproducible
- Test ordering must be consistent across runs

#### FR-103: Portability
- Tests must produce identical results on:
  - Local developer machines (Mac, Linux, Windows with WSL2)
  - CI environments (GitHub Actions)
  - Container environments (Docker, Kubernetes)
- No hardcoded secrets or endpoints in test code
- Service discovery via Service Locator pattern

### 2.2 Test Organization & Discovery

#### FR-201: Profile-Based Testing
- Profiles stored in `profiles/<id>/` directory structure
- Each profile contains:
  - `capabilities.yaml` - capability vector definition
  - `config.yaml` - roles, selection criteria, matrix, timeouts
  - `policies.yaml` - waivers, expected skips, severity levels
- Profiles drive test selection and configuration

#### FR-202: Tagging System
- **Required tags**:
  - `@req:<id>` - Links to business requirement
  - `@cap:<key=value>` - Declares capability being tested
- **Optional tags**:
  - `@risk:<high|medium|low>` - Risk level
  - `@smoke` - Smoke test indicator
  - `@testrail:<case-id>` - TestRail case linkage
  - `@jira:<key>` - Jira issue linkage
- **Forbidden**: `@profile:` tags (profile.id recorded in artifacts instead)

#### FR-203: Test Discovery
- Discover tests by tag combinations
- Support selective execution based on:
  - Impacted BR IDs
  - Smoke test selection
  - Risk-based prioritization (high/medium)
  - Capability coverage requirements

### 2.3 Artifact Management

#### FR-301: Artifact Generation
- Every test scenario/variant must produce:
  - Evidence JSON file
  - Test execution logs
  - Screenshots (for UI tests)
  - Additional attachments as needed
- Artifact storage path template:
  ```
  {run_id}/{req.id}/{profile.id}/{variant}/<timestamp>-<type>.<ext>
  ```

#### FR-302: Evidence JSON Schema
Required fields in evidence.json:
```json
{
  "req_id": "BR-101",
  "profile_id": "cross-sdk-basic",
  "variant": "go-to-java-nano",
  "commit_sha": "abc123...",
  "start_timestamp": "2024-01-15T10:00:00Z",
  "end_timestamp": "2024-01-15T10:01:30Z",
  "status": "passed|failed|skipped",
  "logs": ["path/to/log1.txt"],
  "screenshots": ["path/to/screenshot1.png"],
  "attachments": ["path/to/tdf-sample.tdf"]
}
```

#### FR-303: Artifact Retention
- CI environments: Minimum 14 days retention
- Labeled runs (release/audit): Permanent retention
- Local runs: Configurable retention (default 7 days)

### 2.4 External Integrations

#### FR-401: TestRail Integration
- Automatic test run creation at pipeline start
- Link each test to TestRail case via `@testrail:<case-id>` tag
- Push results including:
  - Pass/Fail status
  - Execution duration
  - Commit SHA
  - Artifact links
- Support bulk result upload

#### FR-402: Jira Integration (Optional)
- Toggle via configuration/environment variable
- On test failure:
  - Create new bug if none exists
  - Update existing bug with new failure
- Include in bug report:
  - Test name and requirement ID
  - Failure logs
  - Screenshots
  - Evidence JSON
  - Environment details

### 2.5 Reporting

#### FR-501: Coverage Matrix Generation
- Generate Feature Coverage Matrix from last 14 days of test runs
- Group coverage by:
  - Business Requirement ID
  - Capability coverage
  - Profile/SDK coverage
- Output formats: HTML, JSON, Markdown

#### FR-502: Test Results Dashboard
- Real-time test execution status
- Historical trend analysis
- Flake rate tracking
- Performance metrics (execution time trends)

## 3. Non-Functional Requirements

### 3.1 Security
- NFR-101: No secrets or credentials in test code or artifacts
- NFR-102: All test data must be sanitized before artifact storage
- NFR-103: Service credentials resolved at runtime via secure storage

### 3.2 Maintainability
- NFR-201: Test code must follow established coding standards
- NFR-202: All test utilities must have unit test coverage >80%
- NFR-203: Configuration changes must not require code changes

### 3.3 Observability
- NFR-301: All test executions must produce structured logs
- NFR-302: Metrics collection for test execution performance
- NFR-303: Distributed tracing support for cross-service tests

### 3.4 Compatibility
- NFR-401: Backward compatibility with existing test suites
- NFR-402: Forward compatibility with planned Phase 2 features
- NFR-403: Support for current SDK versions (Go 1.24, Java 17, Node 22, Swift 6)

## 4. Acceptance Criteria

### 4.1 Performance
- [ ] 10 consecutive CI runs complete within time targets
- [ ] xtest suite completes in ≤10 minutes
- [ ] BDD suite completes in ≤15 minutes

### 4.2 Reliability
- [ ] Flake rate measured <0.5% across 100 test runs
- [ ] Zero hardcoded secrets detected by security scan
- [ ] 100% of tests produce valid evidence JSON

### 4.3 Integration
- [ ] TestRail shows results for all executed tests
- [ ] Artifact links accessible from TestRail
- [ ] Jira bugs created for failures (when enabled)

### 4.4 Coverage
- [ ] 100% of in-scope BR IDs appear in coverage reports
- [ ] Coverage Matrix delivered in all three formats
- [ ] All capability combinations tested per profile

### 4.5 Documentation
- [ ] Test procedure documentation complete
- [ ] Tool usage documentation complete
- [ ] Architecture documentation updated

## 5. Constraints & Assumptions

### Constraints
- Must maintain compatibility with existing CI/CD pipeline
- Cannot modify production code, only test code
- Must work within current GitHub Actions runner limitations
- TestRail API rate limits must be respected

### Assumptions
- Docker and Docker Compose available in all environments
- Network access to TestRail and Jira APIs
- Sufficient CI runner resources for parallelization
- Platform services (KAS, Policy) remain stable

## 6. Dependencies

### External Dependencies
- TestRail Cloud API v2
- Jira Cloud REST API
- Docker Hub for base images
- GitHub Actions for CI execution

### Internal Dependencies
- OpenTDF platform services (xtest/platform)
- SDK implementations (Go, Java, JavaScript, Swift)
- Keycloak for authentication testing
- PostgreSQL for policy database

## 7. Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| TestRail API downtime | High | Low | Queue results for retry, local caching |
| Flaky platform services | High | Medium | Service health checks, automatic restart |
| CI runner resource limits | Medium | Medium | Optimize parallelization, use matrix builds |
| Complex test dependencies | Medium | High | Dependency injection, service mocking |

## 8. Success Metrics

- **Performance**: 90% of test runs complete within target times
- **Reliability**: <0.5% flake rate maintained over 30 days
- **Coverage**: 100% BR coverage for in-scope requirements
- **Adoption**: 100% of new tests follow tagging conventions
- **Quality**: Zero P0 bugs in test framework after launch

## 9. Timeline & Milestones

### Phase 1 Milestones
1. **Week 1-2**: Profile system implementation and migration
2. **Week 3-4**: Artifact management and evidence generation
3. **Week 5-6**: TestRail integration and result publishing
4. **Week 7-8**: Jira integration and bug creation workflow
5. **Week 9-10**: Coverage reporting and dashboard
6. **Week 11-12**: Stabilization and acceptance testing

## 10. Appendices

### A. Glossary
- **BR**: Business Requirement
- **KAS**: Key Access Service
- **TDF**: Trusted Data Format
- **SDK**: Software Development Kit
- **BDD**: Behavior-Driven Development
- **xtest**: Cross-SDK compatibility test suite

### B. Related Documents
- [DESIGN.md](./DESIGN.md) - Technical design specification
- [CLAUDE.md](./CLAUDE.md) - AI assistant context
- [Test Framework Modernization BRD](#) - Business Requirements Document

### C. Change Log
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024-01-15 | System | Initial requirements document |