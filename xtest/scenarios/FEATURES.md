# KAS Preview Features in Scenario Files

This guide documents how to configure KAS preview settings via the `features` dict in scenario YAML files.

## Overview

The `features` dict in a `KasPin` allows scenario authors to enable platform preview settings for specific KAS instances. Features are written to the generated `opentdf.yaml` as `services.kas.preview.<key>: <value>`.

**Important:** Available preview settings depend on the platform version and may include experimental features in PRs. This guide provides common examples but is not exhaustive.

## Basic Usage

```yaml
instance:
  kas:
    km1:
      source: { ref: "pr:3537" }
      mode: key_management
      features:
        hybrid_tdf_enabled: true  # Enable ML-KEM wrapping
```

## Precedence Rules

Features are applied in order (last wins):

1. **Template defaults** — from `opentdf-kas-mode.yaml` shipped with the platform
2. **Mode-based auto-enables** — e.g., `key_management` mode sets `ec_tdf_enabled: true`
3. **User features** — specified in scenario YAML (override previous layers)

This allows you to override mode defaults when needed for testing.

## Common Preview Settings

These examples represent common settings as of 2026-06. Check your platform version's documentation for the complete list.

### `ec_tdf_enabled`

Enables elliptic-curve wrapping for TDF encryption.

- **Auto-enabled:** `key_management` mode
- **When to use:** Testing EC wrapping on standard KAS instances
- **Example:**
  ```yaml
  kas:
    alpha:
      source: { ref: "v0.15.0" }
      mode: standard
      features:
        ec_tdf_enabled: true
  ```

### `hybrid_tdf_enabled`

Enables hybrid post-quantum wrapping (ML-KEM).

- **Auto-enabled:** Never (requires explicit opt-in)
- **When to use:** Testing ML-KEM encryption scenarios
- **Example:**
  ```yaml
  kas:
    km1:
      source: { ref: "pr:3537" }
      mode: key_management
      features:
        hybrid_tdf_enabled: true  # Required for mlkem:768 / mlkem:1024
  ```

### `key_management`

Enables the managed key registry and key provisioning APIs.

- **Auto-enabled:** `key_management` mode
- **When to use:** Rarely needed explicitly (mode handles it)
- **Example (disabling on key_management KAS for testing):**
  ```yaml
  kas:
    km1:
      mode: key_management
      features:
        key_management: false  # Override mode default
  ```

## Example Scenarios

### ML-KEM Encryption Testing

```yaml
instance:
  kas:
    km1:
      source: { ref: "pr:3537" }
      mode: key_management
      features:
        hybrid_tdf_enabled: true  # Accept ML-KEM wrapped KAOs
    km2:
      source: { ref: "pr:3537" }
      mode: key_management
      features:
        hybrid_tdf_enabled: true
```

### EC Wrapping on Standard KAS

```yaml
instance:
  kas:
    alpha:
      source: { ref: "v0.15.0" }
      mode: standard
      features:
        ec_tdf_enabled: true  # Enable EC without key management
```

### Disabling Mode Auto-Enables

```yaml
instance:
  kas:
    km1:
      mode: key_management
      features:
        ec_tdf_enabled: false  # Override mode's auto-enable for testing
```

## Experimental Features in PRs

Platform PRs may introduce experimental preview settings not listed here. Use the same syntax:

```yaml
kas:
  alpha:
    source: { ref: "pr:9999" }
    mode: standard
    features:
      experimental_new_feature: true
```

The scenario framework applies all features without validation, making it forward-compatible with new settings.

## Instance-Level Features

The `Instance.features` dict is reserved for future use. Currently, only per-KAS features are supported:

```yaml
instance:
  features: {}  # Reserved, not implemented
  kas:
    km1:
      features:
        hybrid_tdf_enabled: true  # Use this instead
```

## Verification

After running `otdf-local instance init` and `otdf-local up`, verify the generated config:

```bash
grep -A 5 "preview:" instances/<name>/kas/km1/opentdf.yaml
```

Expected output for a `key_management` KAS with `hybrid_tdf_enabled: true`:

```yaml
preview:
  ec_tdf_enabled: true
  hybrid_tdf_enabled: true
  key_management: true
```

## Troubleshooting

### Feature not appearing in config

1. Check the scenario YAML syntax (YAML indentation matters)
2. Verify `otdf-local instance init` ran without errors
3. Check if the feature exists in your platform version

### Feature value overridden

Remember precedence: user features override mode defaults. If a mode auto-enables a feature and you don't want it, explicitly set it to `false`.

### Unknown feature

Platform versions vary in which preview settings they support. Experimental PRs may have settings not in stable releases. The framework applies all features without validation for forward compatibility.
