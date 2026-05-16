# Agent guidance for xtest/schema

These JSON Schemas are the canonical reference for the on-disk YAML formats. When you need to know what fields a scenario or instance accepts:

- **Read these files**. Don't run `python -c "from otdf_sdk_mgr.schema import ..."` to introspect — those forms aren't in the plugin's allowlist, and the JSON Schemas have the same information in declarative form (titles, types, `anyOf` for ref-vs-version pins, `additionalProperties: false`, default values, etc.).
- The files are byte-stable and sorted; safe to grep, diff, or quote.

If a Pydantic model changes and these files drift, the user (or CI) will regenerate them via `uv run otdf-sdk-mgr schema dump`. Don't try to regenerate them yourself unless you're explicitly fixing the drift in a schema-editing PR.
