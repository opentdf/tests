# Simplify Multi-Instance PR — Design

**Date:** 2026-06-09  
**Branch:** DSPX-3302-03-multi-instance  
**Scope:** Code-quality cleanup within the existing PR; no scope reduction.

## Problem

The multi-instance PR introduces three independent copies of the same binary/worktree resolution logic:

- `KASService._instance_paths()` in `services/kas.py`
- `PlatformService._instance_dist_paths()` in `services/platform.py`
- `_resolve_platform_worktree()` in `cli_instance.py`

All three do: load instance manifest → extract dist string → locate binary under `get_platform_dir()/dist/<dist>/service` → read `.version` file for `worktree=<path>` line → return `(binary, worktree)`.

Additionally:
- `settings.load_instance()` re-reads and parses YAML from disk on every call; it is invoked on nearly every property access in the service classes.
- `Ports` has two parallel lookup tables (`_KAS_NAMES` mapping names to class attributes, and `KAS_OFFSETS` mapping names to ints) that represent the same domain. The legacy constants are numerically equal to `8080 + offset`, so `_KAS_NAMES` is misleading dead weight.

## Design

### 1. `Settings.resolve_binary_worktree(dist: str) -> tuple[Path, Path]`

Add a single method to `Settings` that encapsulates binary-path resolution:

1. Compute `binary = get_platform_dir() / "dist" / dist / "service"`.
2. Raise `FileNotFoundError` with a `otdf-sdk-mgr install` hint if the binary is missing.
3. Read `binary.parent / ".version"` and extract the `worktree=<path>` line if present; fall back to `binary.parent` if the file is absent or has no such line.
4. Return `(binary, worktree)`.

### 2. Cache `load_instance()` on the Settings instance

`load_instance()` stores its result in a private `_instance_cache` attribute on first call (`None` sentinel, `False` meaning "no instance"). Because `Settings` is already invalidated via `get_settings.cache_clear()` whenever `--instance` is set or `scenario run` overrides the instance name, caching on the instance is safe.

### 3. Simplify callers

`KASService._instance_paths()` and `PlatformService._instance_dist_paths()` are reduced to:
- Call `settings.load_instance()` to get the manifest (or `None`).
- Extract the relevant `dist` string (kas pin or platform pin).
- Delegate to `settings.resolve_binary_worktree(dist)`.

`_resolve_platform_worktree()` in `cli_instance.py` is deleted; its callers use `settings.resolve_binary_worktree(dist_name)` directly.

The `if instance_paths is not None: ..., worktree = instance_paths[1]; else: platform_dir = self.settings._require_platform_dir()` fallback pattern remains in both service `_generate_config()` methods — it is now 4–5 lines each and clearly readable.

### 4. Unify `Ports` lookup

Remove `_KAS_NAMES` (the name → class-attribute map) and the duplicated `ALPHA`, `BETA`, … constants that back it. Rewrite `get_kas_port` to always use `KAS_OFFSETS` with a default `base=8080`:

```python
@classmethod
def get_kas_port(cls, name: str, *, base: int = 8080) -> int:
    offset = cls.KAS_OFFSETS.get(name)
    if offset is None:
        raise ValueError(f"Unknown KAS instance: {name}")
    return base + offset
```

The numeric values are unchanged (8080+101=8181, etc.). Any callers that were using the class constants directly (e.g., `Ports.ALPHA`) are updated to `Ports.get_kas_port("alpha")`.

## Files Changed

| File | Change |
|------|--------|
| `otdf-local/src/otdf_local/config/settings.py` | Add `resolve_binary_worktree()`, cache `load_instance()` |
| `otdf-local/src/otdf_local/config/ports.py` | Remove `_KAS_NAMES`, unify `get_kas_port` to use `KAS_OFFSETS` |
| `otdf-local/src/otdf_local/services/kas.py` | Shrink `_instance_paths()` to delegate |
| `otdf-local/src/otdf_local/services/platform.py` | Shrink `_instance_dist_paths()` to delegate |
| `otdf-local/src/otdf_local/cli_instance.py` | Delete `_resolve_platform_worktree()`, inline the simpler call |

## Out of Scope

- Splitting the PR into smaller PRs (user confirmed code quality only).
- Changing the `InstanceContext` dataclass approach (A chosen over B).
- Touching test files or non-`otdf-local` packages.
