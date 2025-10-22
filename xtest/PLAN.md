# Performance Optimization Plan for OpenTDF Test Suite

## Executive Summary
The test suite currently takes ~30 minutes to run with **696 tests collected** across 3 main test files. The primary bottlenecks are:
- Heavy subprocess calls to SDK CLIs (Go, Java, JS)
- Sequential test execution without parallelization
- Extensive SDK version combinations creating massive parameterization
- Module-scoped fixtures that cannot be shared efficiently
- No test categorization or selective execution strategy

---

## 1. Test Execution Parallelization ⚡

### 1.1 Add pytest-xdist for Parallel Execution
**Impact: HIGH (50-75% time reduction)**
- Currently NOT installed (missing from requirements.txt)
- Can run tests in parallel across CPU cores
- Implementation:
  ```bash
  pip install pytest-xdist
  pytest -n auto  # Auto-detect CPU cores
  pytest -n 8     # Explicit worker count
  ```

### 1.2 Ensure Thread-Safety
**Impact: MEDIUM (prerequisite for parallelization)**
- Global `cipherTexts` dictionaries in test_tdfs.py:14 need locking
- Temporary namespace creation (conftest.py:195-199) needs isolation
- File I/O operations need unique paths per worker

### 1.3 Use pytest-xdist Scopes
**Impact: MEDIUM**
- Group tests by module/class to share fixtures
- `--dist loadscope` for better fixture reuse
- `--dist loadfile` for file-level isolation

---

## 2. Fixture Optimization 🔧

### 2.1 Analyze Fixture Scope Efficiency
**Current State:**
- 29 fixtures with `scope="module"` (conftest.py)
- 5 fixtures with `scope="session"`
- Most expensive fixtures (namespace creation, attributes) are module-scoped

**Improvements:**
- Promote expensive setup fixtures to `session` scope where possible
- Examples:
  - `temporary_namespace` (line 194) → session scope with cleanup
  - `temporary_attribute_*` fixtures → session scope
  - `pt_file` generation (line 156) → already optimal

### 2.2 Lazy Fixture Loading
**Impact: MEDIUM**
- Implement lazy evaluation for fixtures only used in subset of tests
- Use `pytest.mark.usefixtures` selectively
- Defer SDK version loading until needed

### 2.3 Fixture Caching Enhancement
**Impact: LOW-MEDIUM**
- Current `cipherTexts` cache (test_tdfs.py:14) is good but limited
- Expand to cache:
  - Attribute definitions
  - KAS configurations
  - Policy evaluations

---

## 3. Test Organization & Selective Execution 🎯

### 3.1 Implement Test Markers
**Impact: HIGH (enables targeted runs)**
- Add markers for test categories:
  ```python
  @pytest.mark.fast        # < 1 second
  @pytest.mark.slow        # > 5 seconds
  @pytest.mark.encryption  # Tests encrypt operations
  @pytest.mark.decryption  # Tests decrypt operations
  @pytest.mark.abac        # Policy tests
  @pytest.mark.integration # Full SDK integration
  @pytest.mark.unit        # Isolated logic
  ```

### 3.2 SDK Version Matrix Reduction
**Impact: HIGH (reduce test count from 696)**
- Current: All SDK combinations (go@v0.24.0, go@main, js@v0.4.0, js@main, java variants)
- Strategy:
  - **Smoke tests**: One version combination per SDK (reduce 80% of tests)
  - **Compatibility matrix**: Weekly/nightly runs for full cross-version
  - **Focus mode**: Already exists (conftest.py:133-143) - promote usage

### 3.3 Container Format Optimization
**Impact: MEDIUM**
- Current: Tests run against multiple containers (nano, ztdf, nano-with-ecdsa, ztdf-ecwrap)
- Strategy:
  - Default runs: Single container format
  - Extended runs: All formats
  - Use `--containers` flag (conftest.py:65-68) more effectively

---

## 4. SDK/Platform Interaction Optimization 🚀

### 4.1 Subprocess Call Optimization
**Impact: HIGH**
- **Current bottleneck:** 
  - tdfs.py:389, 428, 430 - `subprocess.check_call/check_output`
  - abac.py:265+ - Multiple `subprocess.Popen` calls
  
**Improvements:**
- Batch operations where possible
- Reuse SDK process instances (keep-alive pattern)
- Pre-warm SDK environments (module-level setup)
- Use async subprocess calls with `asyncio.create_subprocess_exec()`

### 4.2 Platform API Call Batching
**Impact: MEDIUM**
- Group attribute/namespace creation into batch operations
- Implement GraphQL batching if platform supports it
- Cache platform responses for identical queries

### 4.3 Skip Redundant Feature Checks
**Impact: LOW-MEDIUM**
- Cache `_uncached_supports()` results (tdfs.py:438) at session level
- Pre-compute SDK feature matrices before test run

---

## 5. Test Data Management 📦

### 5.1 Pre-generate Test Artifacts
**Impact: MEDIUM**
- Generate plaintext files once at session start
- Pre-encrypt "golden" TDF files for decrypt-only tests
- Store in shared temp directory with session scope

### 5.2 Optimize File Sizes
**Impact: LOW**
- Current small file: 128 bytes (conftest.py:159)
- Consider even smaller for fast tests (16-32 bytes)
- Large file tests (5GB): Keep optional via `--large` flag (good!)

### 5.3 Leverage Golden Files
**Impact: MEDIUM**
- Directory exists: `golden/*.tdf`
- Use pre-encrypted golden files for decrypt tests
- Eliminates encrypt step for pure decryption tests

---

## 6. Infrastructure & Configuration ⚙️

### 6.1 Pytest Configuration
**Missing:** No pytest.ini or pyproject.toml configuration
**Add:**
```ini
[tool:pytest]
# Parallel execution
addopts = -n auto --dist loadscope

# Test discovery
testpaths = .
python_files = test_*.py
python_functions = test_*

# Markers
markers =
    fast: Fast tests (< 1s)
    slow: Slow tests (> 5s)
    encryption: Tests encryption operations
    decryption: Tests decryption operations
    abac: Attribute-based access control tests
    integration: Full integration tests
    smoke: Smoke test suite

# Reporting
junit_family = xunit2

# Timeout
timeout = 300
```

### 6.2 Environment Variable Optimization
**Impact: LOW**
- Document required env vars (test.env exists but check usage)
- Use environment-specific defaults
- Cache environment setup

### 6.3 CI/CD Pipeline Optimization
**Impact: HIGH (if CI/CD exists)**
- Matrix strategy: Parallelize SDK combinations across CI jobs
- Caching: Cache SDK binaries, dependencies
- Tiered testing: PR (fast), Nightly (full), Weekly (compatibility matrix)

---

## 7. Code-Level Optimizations 💻

### 7.1 Reduce Pytest Collection Time
**Current: 0.04s for 696 tests (GOOD)**
- No immediate action needed

### 7.2 Optimize Assertions Module
**Impact: LOW**
- assertions.py (imported in conftest.py:8) - check for heavy operations
- Ensure validation logic is efficient

### 7.3 Profile Individual Tests
**Impact: HIGH (diagnostic)**
```bash
pytest --profile
pytest --durations=10  # Show 10 slowest tests
```

---

## 8. Recommended Implementation Phases 📅

### Phase 1: Quick Wins (1-2 days)
1. Add pytest-xdist to requirements.txt
2. Run with `pytest -n auto` (immediate 50-70% speedup)
3. Add test markers (fast/slow/smoke)
4. Document `--focus` and `--sdks` options for developers

### Phase 2: Fixture Optimization (3-5 days)
1. Promote expensive fixtures to session scope
2. Add thread-safety to global caches
3. Implement lazy fixture loading
4. Pre-generate test artifacts

### Phase 3: Test Organization (1 week)
1. Create smoke test suite (10% of tests, 90% coverage)
2. Implement tiered test strategy
3. Add pytest.ini configuration
4. Document test execution strategies

### Phase 4: SDK Optimization (1-2 weeks)
1. Batch subprocess operations
2. Implement SDK process reuse
3. Add async subprocess support
4. Optimize platform API calls

### Phase 5: Advanced (2+ weeks)
1. CI/CD matrix parallelization
2. Golden file strategy expansion
3. Custom pytest plugin for TDF testing
4. Profiling and continuous optimization

---

## 9. Expected Performance Improvements 📊

| Optimization | Time Reduction | Effort | Priority |
|---|---|---|---|
| pytest-xdist (8 cores) | 50-70% | Low | **CRITICAL** |
| Test markers + smoke suite | 80-90% (dev workflow) | Low | **HIGH** |
| Session-scoped fixtures | 10-20% | Medium | HIGH |
| SDK subprocess optimization | 15-30% | High | MEDIUM |
| Container format reduction | 20-30% (configurable) | Low | MEDIUM |
| Golden file usage | 10-15% | Medium | MEDIUM |
| Async subprocess | 20-40% | High | LOW |

**Combined Impact (Phases 1-3):**
- Full run: 30 min → **5-8 minutes**
- Smoke tests: **< 2 minutes**
- Focused SDK run: **< 5 minutes**

---

## 10. Monitoring & Maintenance 📈

### 10.1 Add Performance Tracking
- Integrate pytest-benchmark for regression detection
- Track test duration trends
- Alert on performance degradation

### 10.2 Regular Profiling
- Monthly: Run `pytest --durations=20`
- Identify new slow tests
- Refactor or mark appropriately

### 10.3 Documentation
- Create TESTING.md with:
  - Quick start commands
  - Test selection strategies
  - Performance tips
  - CI/CD integration guide

---

## Summary: Top 5 Action Items

1. **Install pytest-xdist** → Run `pytest -n auto` (50-70% speedup, 1 hour effort)
2. **Add test markers** → Enable smoke/fast/slow test selection (80-90% dev speedup, 4 hours)
3. **Promote fixtures to session scope** → Reduce setup overhead (10-20% speedup, 1 day)
4. **Document SDK selection flags** → Use `--focus`, `--sdks` for targeted runs (immediate, 1 hour)
5. **Create pytest.ini** → Standardize configuration and defaults (immediate, 30 min)

**Total estimated effort for 70%+ improvement: 2-3 days**
