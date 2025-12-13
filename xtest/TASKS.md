# OpenTDF Test Suite Optimization - Task Breakdown

## Overview
This document breaks down the comprehensive performance optimization plan into actionable tasks. Tasks are organized into phases with clear priorities and dependencies. Review and check off tasks as they are completed.

---

## Phase 1: Quick Wins (Target: 1-2 days, 50-70% improvement)

### 1.1 Test Parallelization Setup ✅ COMPLETED
- [x] Add `pytest-xdist` to requirements.txt
- [x] Test basic parallel execution with `pytest -n auto`
- [x] Verify all tests pass with parallelization enabled
- [x] Document any test failures or issues with parallel execution
- [x] Identify and fix any tests with race conditions or shared state issues

**Expected Outcome:** Immediate 50-70% speedup on multi-core systems

**Results:**
- pytest-xdist successfully integrated
- Parallel execution working correctly with `-n auto`
- No race conditions or data corruption detected
- Global state issues identified and documented in PARALLEL_EXECUTION_FINDINGS.md
- Tests pass reliably with parallel execution
- Cache sharing optimization deferred to Phase 2 (will provide full performance benefit)

---

## Phase 2: Configuration & Infrastructure (Target: 2-3 days)

### 2.1 Pytest Configuration File
- [ ] Create `pytest.ini` or add `[tool.pytest]` section to `pyproject.toml`
- [ ] Configure default parallel execution settings
- [ ] Register all test markers
- [ ] Set up test discovery patterns
- [ ] Configure timeout settings (300s default)
- [ ] Add junit_family configuration for CI/CD compatibility
- [ ] Test configuration and verify expected behavior

**Expected Outcome:** Standardized test execution with sensible defaults

---

### 2.2 Process Isolation Strategy (Filesystem-based Caching)
- [ ] Audit current usage of global `cipherTexts` dictionaries (test_tdfs.py:14)
- [ ] Design filesystem-based cache structure:
  - [ ] Choose cache directory location (e.g., `.pytest_cache/xdist_shared/`)
  - [ ] Define cache key format (hash of test parameters)
  - [ ] Define cache file naming convention
- [ ] Implement filesystem cache manager:
  - [ ] Create cache read/write functions with file locking
  - [ ] Add cache hit/miss logging for monitoring
  - [ ] Implement cache expiration/cleanup logic
  - [ ] Handle concurrent access with file locks (fcntl or similar)
- [ ] Replace in-memory `cipherTexts` cache with filesystem cache:
  - [ ] Update cache writes after TDF encryption
  - [ ] Update cache reads before TDF decryption
  - [ ] Ensure backward compatibility for non-parallel runs
- [ ] Test with multiple xdist workers to verify cross-process sharing:
  - [ ] Run with `-n 2`, `-n 4`, `-n auto`
  - [ ] Verify cache hits across workers
  - [ ] Check for race conditions or corrupted cache files
- [ ] Add cache statistics and monitoring:
  - [ ] Track cache hit rate
  - [ ] Log cache size and cleanup events
- [ ] Document the filesystem caching strategy:
  - [ ] Document cache location and structure
  - [ ] Document cache lifecycle and cleanup
  - [ ] Add troubleshooting guide for cache issues

**Expected Outcome:** Efficient resource sharing across parallel test workers using filesystem-based cache

---

### 2.3 xdist Scope Optimization
- [ ] Experiment with `--dist loadscope` for fixture reuse
- [ ] Experiment with `--dist loadfile` for file-level isolation
- [ ] Measure performance impact of different distribution strategies
- [ ] Document recommended distribution strategy
- [ ] Update pytest.ini with optimal default

**Expected Outcome:** Better fixture reuse and reduced setup overhead

---

## Phase 3: Fixture Optimization (Target: 3-5 days, 10-20% improvement)

### 3.1 Fixture Scope Analysis
- [ ] Profile current fixture execution times
- [ ] Identify fixtures that are safe to promote to session scope
- [ ] Review `temporary_namespace` (conftest.py:194) for session scope promotion
- [ ] Review `temporary_attribute_*` fixtures for session scope promotion
- [ ] Ensure proper cleanup for session-scoped fixtures
- [ ] Test with session-scoped fixtures to verify no test interference

**Expected Outcome:** Reduced fixture setup/teardown overhead

---

### 3.2 Fixture Caching Enhancement
- [ ] Expand caching beyond current `cipherTexts` dictionary
- [ ] Implement caching for attribute definitions
- [ ] Implement caching for KAS configurations
- [ ] Implement caching for policy evaluations
- [ ] Add cache invalidation logic where needed
- [ ] Document caching behavior and limitations

**Expected Outcome:** Reduced redundant API calls and operations

---

### 3.3 Lazy Fixture Loading
- [ ] Identify fixtures used only by subset of tests
- [ ] Refactor to use `pytest.mark.usefixtures` selectively
- [ ] Defer expensive SDK version loading until actually needed
- [ ] Test impact on test execution time
- [ ] Document lazy loading patterns

**Expected Outcome:** Reduced unnecessary fixture initialization

---

## Phase 4: Test Organization & Selective Execution (Target: 1 week, 80-90% dev workflow improvement)

### 4.1 Smoke Test Suite Creation
- [ ] Identify 10% of tests that provide 90% coverage
- [ ] Mark identified tests with `@pytest.mark.smoke`
- [ ] Verify smoke suite runs in < 2 minutes
- [ ] Document smoke test suite purpose and usage
- [ ] Add smoke test run to quick developer workflow documentation

**Expected Outcome:** Fast feedback loop for developers (< 2 min runs)

---

### 4.2 SDK Version Matrix Reduction
- [ ] Review current SDK version combinations
- [ ] Define "smoke" versions (one per SDK) for quick runs
- [ ] Define "full matrix" for comprehensive testing
- [ ] Implement version selection strategy (CLI flag or environment variable)
- [ ] Document when to use smoke vs full matrix
- [ ] Update CI/CD to use appropriate matrix per job type

**Expected Outcome:** 80% reduction in test count for typical dev runs

---

### 4.3 Container Format Strategy
- [ ] Audit current container format parameterization
- [ ] Define default container format for quick runs
- [ ] Document when to test all container formats
- [ ] Improve `--containers` flag documentation
- [ ] Add container format strategy to TESTING.md

**Expected Outcome:** Configurable test breadth based on needs

---

### 4.4 Tiered Testing Strategy
- [ ] Define "PR tests" tier (smoke + critical path)
- [ ] Define "Nightly" tier (full test suite, focused SDK versions)
- [ ] Define "Weekly" tier (full compatibility matrix)
- [ ] Document each tier's purpose and expected runtime
- [ ] Create helper scripts or make targets for each tier
- [ ] Update CI/CD configuration to implement tiers

**Expected Outcome:** Right level of testing at the right time

---

## Phase 5: SDK/Platform Optimization (Target: 1-2 weeks, 15-30% improvement)

### 5.1 Subprocess Call Audit
- [ ] Profile subprocess calls to identify bottlenecks
- [ ] Document current subprocess patterns in tdfs.py:389, 428, 430
- [ ] Document current subprocess patterns in abac.py:265+
- [ ] Identify opportunities for batching operations
- [ ] Identify opportunities for process reuse

**Expected Outcome:** Clear understanding of subprocess overhead

---

### 5.2 Subprocess Call Optimization
- [ ] Implement batching for operations that can be grouped
- [ ] Implement SDK process keep-alive pattern where possible
- [ ] Add module-level SDK environment pre-warming
- [ ] Test optimizations and measure performance impact
- [ ] Document subprocess optimization patterns

**Expected Outcome:** Reduced subprocess spawn overhead

---

### 5.3 Platform API Call Batching
- [ ] Identify repeated attribute/namespace creation calls
- [ ] Implement batch creation operations
- [ ] Investigate GraphQL batching support in platform
- [ ] Implement response caching for identical queries
- [ ] Measure API call reduction

**Expected Outcome:** Reduced API round-trips to platform

---

### 5.4 Feature Check Optimization
- [ ] Review `_uncached_supports()` in tdfs.py:438
- [ ] Move feature check results to session-level cache
- [ ] Pre-compute SDK feature matrices at test session start
- [ ] Verify caching works correctly across test runs
- [ ] Document feature check caching behavior

**Expected Outcome:** Eliminate redundant SDK capability checks

---

### 5.5 Async Subprocess Support (Optional)
- [ ] Evaluate feasibility of async subprocess calls
- [ ] Prototype with `asyncio.create_subprocess_exec()`
- [ ] Measure performance improvement
- [ ] Implement if improvement justifies complexity
- [ ] Document async patterns if implemented

**Expected Outcome:** 20-40% improvement if implemented (high effort)

---

## Phase 6: Test Data Management (Target: 3-5 days, 10-15% improvement)

### 6.1 Test Artifact Pre-generation
- [ ] Identify test artifacts that can be pre-generated
- [ ] Generate plaintext files at session start (once)
- [ ] Create shared temp directory with session scope
- [ ] Update tests to use pre-generated artifacts
- [ ] Measure impact on test setup time

**Expected Outcome:** Reduced redundant file generation

---

### 6.2 Golden File Strategy
- [ ] Audit existing golden files in `golden/` directory
- [ ] Identify decrypt-only tests that can use golden files
- [ ] Refactor tests to use pre-encrypted golden TDFs
- [ ] Generate additional golden files for common test scenarios
- [ ] Document golden file usage and maintenance

**Expected Outcome:** Eliminate encrypt step for pure decrypt tests

---

### 6.3 File Size Optimization
- [ ] Review current test file sizes (128 bytes small file)
- [ ] Experiment with even smaller files (16-32 bytes) for fast tests
- [ ] Verify file size changes don't affect test validity
- [ ] Document file size strategy
- [ ] Keep large file tests (5GB) behind `--large` flag (already good)

**Expected Outcome:** Faster I/O for small file tests

---

## Phase 7: Monitoring & Maintenance (Ongoing)

### 7.1 Performance Tracking Setup
- [ ] Research `pytest-benchmark` integration
- [ ] Add pytest-benchmark to requirements.txt
- [ ] Add benchmark tests for critical paths
- [ ] Set up performance regression alerts
- [ ] Document how to run benchmark tests

**Expected Outcome:** Automated performance regression detection

---

### 7.2 Regular Profiling Process
- [ ] Schedule monthly profiling runs (`pytest --durations=20`)
- [ ] Create process for reviewing slow tests
- [ ] Define criteria for refactoring slow tests
- [ ] Document profiling process and tools
- [ ] Add profiling commands to TESTING.md

**Expected Outcome:** Proactive performance management

---

### 7.3 Documentation Creation
- [ ] Create comprehensive TESTING.md with:
  - Quick start commands
  - Test selection strategies  
  - Performance tips
  - CI/CD integration guide
  - Troubleshooting common issues
  - Marker reference
  - Fixture reference
- [ ] Update README.md with links to TESTING.md
- [ ] Add examples of different test execution modes

**Expected Outcome:** Self-service documentation for developers

---

## Phase 8: Advanced Optimizations (Target: 2+ weeks, Optional)

### 8.1 CI/CD Pipeline Optimization
- [ ] Audit current CI/CD configuration (if exists)
- [ ] Implement matrix strategy to parallelize SDK combinations
- [ ] Set up caching for SDK binaries
- [ ] Set up caching for Python dependencies
- [ ] Implement tiered testing (PR/Nightly/Weekly)
- [ ] Measure CI/CD performance improvement

**Expected Outcome:** Faster CI/CD feedback, better resource utilization

---

### 8.2 Custom Pytest Plugin (Optional)
- [ ] Design custom plugin for TDF-specific testing needs
- [ ] Implement plugin functionality
- [ ] Test plugin with existing test suite
- [ ] Document plugin usage
- [ ] Consider open-sourcing plugin

**Expected Outcome:** Better testing abstractions for TDF operations

---

### 8.3 Code-Level Optimizations
- [ ] Profile assertions.py for heavy operations
- [ ] Optimize validation logic where needed
- [ ] Review test collection time (currently 0.04s - good)
- [ ] Identify any other code-level bottlenecks
- [ ] Implement optimizations as needed

**Expected Outcome:** Marginal improvements to test execution

---

## Success Metrics

### Performance Targets
- **Phase 1 Complete:** Full run 30 min → 10-15 minutes
- **Phase 2-3 Complete:** Full run → 8-10 minutes
- **Phase 4 Complete:** 
  - Smoke tests: < 2 minutes
  - Focused SDK run: < 5 minutes
- **Phase 5 Complete:** Full run → 5-8 minutes
- **Phase 6 Complete:** Smoke tests: < 1 minute

### Quality Metrics
- [ ] All 696 tests continue to pass
- [ ] No test flakiness introduced
- [ ] No reduction in test coverage
- [ ] Improved developer experience
- [ ] Clear documentation for all test execution modes

---

## Dependencies & Prerequisites

### External Dependencies
- pytest-xdist (Phase 1)
- pytest-benchmark (Phase 7)
- Access to platform API for testing
- SDK binaries (Go, Java, JS)

### Internal Dependencies
- Phase 2 (Process Isolation) must complete before Phase 1 can be fully effective
- Phase 3 (Fixtures) should complete before Phase 4 (Test Organization)
- Phase 4 (Organization) should complete before Phase 5 (SDK Optimization)

---

## Notes

- **Review Points:** Suggested after Phase 1, Phase 3, Phase 4, and Phase 5
- **Rollback Strategy:** Each phase should be implemented in a separate branch/PR for easy rollback
- **Testing:** After each phase, run full test suite to verify no regressions
- **Documentation:** Update TESTING.md incrementally as features are added

---

## Quick Reference - Top Priority Items

1. **Install pytest-xdist** (Phase 1.1) - 1 hour effort, 50-70% speedup
2. **Create pytest.ini** (Phase 2.1) - 30 min effort, standardize config
3. **Fix process isolation** (Phase 2.2) - 1 day effort, enable effective parallelization
4. **Promote fixtures to session scope** (Phase 3.1) - 1 day effort, 10-20% speedup
5. **Optimize subprocess calls** (Phase 5.2) - 3-5 days effort, 15-30% speedup

**Total effort for 70%+ improvement: 2-3 days**
