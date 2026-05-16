# xtest/schema

JSON Schemas for the canonical scenario / instance YAML formats. One file per Pydantic model in `otdf-sdk-mgr/src/otdf_sdk_mgr/schema.py`:

- `scenario.schema.json` — the shape that `xtest/scenarios/<id>.yaml` validates against.
- `instance.schema.json` — the shape of `tests/instances/<name>/instance.yaml`.

These files are generated artifacts. To refresh them after editing a Pydantic model:

```bash
uv run --project otdf-sdk-mgr otdf-sdk-mgr schema dump
```

A pytest in `otdf-sdk-mgr/tests/test_schema_sync.py` fails CI if the committed files drift from what the live models would produce.

See `CLAUDE.md` for how Claude Code skills consume these files.
