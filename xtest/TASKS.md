# Test Suite Performance Optimization Tasks

**Goal:** Reduce test execution time from ~30 minutes to 5-8 minutes (full run) and < 2 minutes (smoke tests)

**Current Status:** 696 tests collected across test_tdfs.py and test_policytypes.py

---

## Phase 1: Quick Wins (1-2 days) ⚡ - ✅ COMPLETED

**Results:** 3x speedup (66% reduction) with parallel execution on 14 workers
- Sequential: 108.91s for 100 tests
- Parallel: 36.56s for 100 tests

### 1.1 Parallel Execution Setup
- [x] Add `pytest-xdist` to requirements.txt
- [x] Install pytest-xdist in virtual environment
- [x] Test basic parallel execution with `pytest -n auto`
- [x] Verify tests pass with parallel execution (all 240 smoke tests pass)
- [x] Benchmark performance improvement
  - **Sequential:** 107.57s for 100 smoke+roundtrip tests (FOCUS_SDK=go@main)
  - **Parallel (14 workers):** 37.95s for same tests  
  - **Speedup:** 2.8x faster (65% reduction in execution time)
  - **Full smoke suite:** 240 tests pass in 167.01s with parallel execution

### 1.2 Thread-Safety Fixes
- [x] Add thread-safe locking to global `cipherTexts` dictionary (test_tdfs.py:14)
- [x] Review temporary namespace creation for worker isolation (conftest.py:195-199)
- [x] Ensure file I/O operations use unique paths per worker
- [x] Test parallel execution stability
- [x] Fix tmp_dir fixture to use worker-specific directories (conftest.py:167)

### 1.3 Test Markers Implementation
- [x] Add marker definitions to pytest.ini (or pyproject.toml)
- [ ] Tag tests with `@pytest.mark.fast` for tests < 1 second (deferred - need profiling)
- [ ] Tag tests with `@pytest.mark.slow` for tests > 5 seconds (deferred - need profiling)
- [x] Add `@pytest.mark.smoke` for critical path tests
- [x] Add domain markers: `encryption`, `decryption`, `abac`, `integration`
- [ ] Document marker usage in README or TESTING.md

### 1.4 Documentation
- [x] Document `--focus` flag usage (conftest.py:133-143)
- [x] Document `--sdks` flag for SDK selection
- [x] Document `--containers` flag for container format selection (conftest.py:65-68)
- [x] Create quick reference for common test execution patterns
- [x] Document parallel execution recommendations

### 1.5 Configuration
- [x] Create pytest.ini or update pyproject.toml with test configuration
- [x] Set default parallel execution options
- [x] Configure marker definitions
- [x] Set test discovery paths
- [x] Configure reporting options

---

## Phase 2: Fixture Optimization (3-5 days) 🔧 - ✅ COMPLETED

**Results:** 14 fixtures promoted to session scope + comprehensive caching analysis
- Full smoke tests: 171.82s for 240 tests (parallel, 14 workers)
- Test suite now optimally configured for parallel execution
- Caching, lazy loading, and data pre-generation already optimal

### 2.1 Fixture Scope Analysis ✅ COMPLETED
- [x] Audit all 39 fixtures in conftest.py (32 module-scoped, 7 session-scoped)
- [x] Identify fixtures safe to promote to session scope
- [x] Document fixture dependencies and constraints
- [x] Created FIXTURE_ANALYSIS.md with comprehensive analysis

### 2.2 Session-Scoped Fixture Promotion - ✅ COMPLETED
#### 2.2a: Low-Risk Fixture Promotion (14 fixtures)
- [x] Promote `otdfctl` (line 193) - global singleton
- [x] Promote `hs256_key` (line 855) - static key generation
- [x] Promote `rs256_keys` (line 860) - static key pair generation
- [x] Promote 5 KAS entry fixtures (lines 292, 306, 320, 334, 348)
- [x] Promote 2 public key fixtures (lines 368, 379)
- [x] Promote 3 assertion fixtures (lines 898, 918, 974)
- [x] Promote `otdf_client_scs` (line 996)
- [x] Test fixture behavior with parallel execution (240 smoke tests pass)
- [x] Verify no scope mismatch errors

#### 2.2b: Module-Scoped Attribute Fixtures (11 fixtures) - DEFERRED
**Decision needed:** Keep at module-scope or promote with shared namespace?
- [ ] Evaluate `temporary_namespace` (line 199) for session scope promotion
- [ ] Consider promoting 11 attribute fixtures if namespace is promoted
- [ ] Risk: Shared namespace across all tests vs isolated per-module
- [ ] Recommendation: Wait for user decision after Phase 2.2a verification

### 2.3 Fixture Caching Enhancement ✅ COMPLETED
- [x] Review current `cipherTexts` cache implementation (test_tdfs.py:14-18)
  - Already thread-safe with `threading.Lock()`
  - Caches encrypted files by container_id to avoid re-encryption
  - Same pattern in test_policytypes.py:13-14
- [x] Review attribute definitions caching
  - Already handled by pytest fixture caching (module/session scope)
- [x] Review KAS configurations caching
  - Uses idempotent `create_if_not_present` API calls
  - Session-scoped fixtures ensure single creation per test run
- [x] Review policy evaluations caching
  - Not applicable - policy evaluation is inherent to each test
- [x] Ensure cache thread-safety
  - All global caches use `threading.Lock()` for thread safety

**Findings:** Caching is already well-implemented. No additional work needed.

### 2.4 Lazy Fixture Loading ✅ COMPLETED
- [x] Identify fixtures only used in subset of tests
  - Assertion fixtures: Only 6 tests out of 696 total
  - Attribute fixtures: Used by specific policy type tests
  - All fixtures are already lazily loaded by pytest (only created when needed)
- [x] Review SDK version loading
  - SDK initialization is lightweight (only checks file existence)
  - SDK objects created on-demand via pytest parametrization
- [x] Review conditional fixture loading
  - Pytest already handles conditional loading via fixture dependencies

**Findings:** Pytest's built-in lazy loading is sufficient. No additional work needed.

### 2.5 Test Data Pre-generation ✅ COMPLETED
- [x] Review plaintext test file generation
  - `pt_file` fixture (line 157) already session-scoped
  - Generates once per worker, reused across all tests
- [x] Review temp directory setup
  - `tmp_dir` fixture (line 167) already session-scoped
  - Worker-isolated directories prevent conflicts
- [x] Review golden TDF files
  - 7 golden files already exist in `golden/` directory
  - Used by test_legacy.py for backwards compatibility testing
- [x] Review pre-encryption opportunities
  - `cipherTexts` cache already handles this efficiently
  - First test encrypts, subsequent tests reuse cached file

**Findings:** Test data generation is already optimized. No additional work needed.

---

## Phase 3: Test Organization (1 week) 🎯

### 3.1 Smoke Test Suite Creation
- [ ] Identify critical path tests (10% of tests, 90% coverage)
- [ ] Tag smoke tests with `@pytest.mark.smoke`
- [ ] Create smoke test execution command
- [ ] Document smoke test purpose and usage
- [ ] Benchmark smoke test execution time (target: < 2 minutes)

### 3.2 SDK Version Matrix Reduction
- [ ] Document current SDK version combinations being tested
- [ ] Define smoke test SDK matrix (one version per SDK)
- [ ] Define full compatibility matrix for extended runs
- [ ] Update test parameterization to support reduced matrix
- [ ] Document when to use each matrix strategy

### 3.3 Container Format Strategy
- [ ] Document current container formats tested (nano, ztdf, nano-with-ecdsa, ztdf-ecwrap)
- [ ] Define default container format for fast runs
- [ ] Define extended container format matrix
- [ ] Document `--containers` flag usage patterns
- [ ] Update test selection to support container strategies

### 3.4 Tiered Testing Strategy
- [ ] Define "fast" tier: smoke tests, single SDK/container combo
- [ ] Define "standard" tier: common SDK versions, key container formats
- [ ] Define "full" tier: all combinations for nightly/weekly runs
- [ ] Document execution commands for each tier
- [ ] Create example CI/CD configuration for tiers

### 3.5 Test Execution Documentation
- [ ] Create TESTING.md document
- [ ] Document quick start commands
- [ ] Document test selection strategies
- [ ] Document performance tips and best practices
- [ ] Add troubleshooting section

---

## Phase 4: SDK Optimization (1-2 weeks) 🚀

### 4.1 Subprocess Analysis
- [ ] Profile subprocess call frequency and duration
- [ ] Identify bottleneck subprocess calls (tdfs.py:389, 428, 430; abac.py:265+)
- [ ] Measure baseline subprocess overhead

### 4.2 Subprocess Call Optimization
- [ ] Identify operations that can be batched
- [ ] Implement batching for encrypt/decrypt operations
- [ ] Reduce redundant subprocess invocations
- [ ] Add error handling for batched operations

### 4.3 SDK Process Reuse
- [ ] Design keep-alive pattern for SDK processes
- [ ] Implement process pooling for SDK CLIs
- [ ] Add process warm-up at module/session level
- [ ] Handle process lifecycle and cleanup

### 4.4 Async Subprocess Support (Optional)
- [ ] Evaluate feasibility of async subprocess calls
- [ ] Implement `asyncio.create_subprocess_exec()` for independent operations
- [ ] Update test infrastructure to support async operations
- [ ] Benchmark async vs sync performance

### 4.5 Feature Detection Caching
- [ ] Cache `_uncached_supports()` results at session level (tdfs.py:438)
- [ ] Pre-compute SDK feature matrices before test run
- [ ] Store feature matrix in session-scoped fixture
- [ ] Update feature checks to use cached data

### 4.6 Platform API Optimization
- [ ] Analyze platform API call patterns
- [ ] Group attribute/namespace creation into batch operations
- [ ] Implement response caching for identical queries
- [ ] Evaluate GraphQL batching if supported

---

## Phase 5: Advanced Optimizations (2+ weeks) 🎓

### 5.1 Golden File Strategy
- [ ] Audit existing golden files in `golden/` directory
- [ ] Expand golden file coverage for common test scenarios
- [ ] Update decrypt-only tests to use golden files
- [ ] Measure encryption step elimination impact
- [ ] Document golden file maintenance procedures

### 5.2 File Size Optimization
- [ ] Review current test file sizes (small: 128 bytes)
- [ ] Experiment with smaller files for fast tests (16-32 bytes)
- [ ] Verify functionality with reduced file sizes
- [ ] Keep large file tests (5GB) optional via `--large` flag
- [ ] Document file size rationale

### 5.3 CI/CD Pipeline Optimization
- [ ] Design matrix strategy for parallelizing SDK combinations
- [ ] Implement caching for SDK binaries and dependencies
- [ ] Create tiered testing jobs: PR (fast), Nightly (full), Weekly (compatibility)
- [ ] Add performance regression detection
- [ ] Document CI/CD configuration

### 5.4 Performance Monitoring
- [ ] Integrate pytest-benchmark for regression detection
- [ ] Set up test duration tracking and trending
- [ ] Configure alerts for performance degradation
- [ ] Create performance dashboard or report

### 5.5 Regular Profiling Process
- [ ] Document profiling commands (`pytest --durations=20`)
- [ ] Establish monthly profiling schedule
- [ ] Create process for identifying and addressing slow tests
- [ ] Track optimization effectiveness over time

### 5.6 Custom Pytest Plugin (Optional)
- [ ] Evaluate need for custom pytest plugin for TDF testing
- [ ] Design plugin architecture
- [ ] Implement common TDF test utilities
- [ ] Package and document plugin

---

## Phase 6: Validation & Refinement 🔍

### 6.1 Performance Benchmarking
- [ ] Benchmark baseline performance (before optimizations)
- [ ] Benchmark after Phase 1 completion
- [ ] Benchmark after Phase 2 completion
- [ ] Benchmark after Phase 3 completion
- [ ] Benchmark after Phase 4 completion
- [ ] Compare results against targets

### 6.2 Stability Testing
- [ ] Run full test suite 10+ times to verify stability
- [ ] Test parallel execution with varying worker counts
- [ ] Verify fixture cleanup with session scope changes
- [ ] Check for race conditions or flaky tests
- [ ] Document any known issues or limitations

### 6.3 Documentation Review
- [ ] Verify all documentation is accurate and complete
- [ ] Add examples for common use cases
- [ ] Include troubleshooting tips
- [ ] Update README with performance improvements
- [ ] Create developer onboarding guide

---

## Success Metrics 📊

### Performance Targets
- [ ] Full test suite: 30 min → 5-8 minutes (70-85% reduction)
- [ ] Smoke test suite: < 2 minutes
- [ ] Focused SDK run: < 5 minutes
- [ ] Fast test subset: < 30 seconds

### Quality Targets
- [ ] Zero test failures introduced by optimizations
- [ ] No flaky tests due to parallel execution
- [ ] All fixtures properly cleaned up
- [ ] Thread-safety verified

### Developer Experience
- [ ] Clear documentation for all test execution modes
- [ ] Easy-to-use smoke test command
- [ ] Quick feedback loop for development
- [ ] CI/CD integration documented

---

## Notes

- Tasks are organized by phase, but some tasks may be reordered based on dependencies
- Check off tasks as completed: `- [x]`
- Add notes or blockers inline as needed
- Estimated effort is cumulative across all phases
- Phases 1-3 provide the most significant improvements (70%+ speedup)
- Phases 4-5 are incremental improvements for marginal gains
