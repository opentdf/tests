"""Guard that the committed JSON Schemas under xtest/schema/ stay in sync
with the live Pydantic models.

The skills authoring scenarios read those JSON files directly to know what
fields are allowed; if a Pydantic model gains, loses, or renames a field
without a corresponding `uv run otdf-sdk-mgr schema dump`, the skills will
silently rely on a stale schema. This test makes that drift loud.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from otdf_sdk_mgr.cli_schema import SCHEMAS, render


def _xtest_schema_dir() -> Path:
    """Locate xtest/schema/ relative to this test file.

    The repo layout puts otdf-sdk-mgr/tests/ next to xtest/, so two parents
    up from this file is the tests/ root.
    """
    return Path(__file__).resolve().parents[2] / "xtest" / "schema"


@pytest.mark.parametrize(("model", "filename"), SCHEMAS, ids=lambda v: getattr(v, "__name__", v))
def test_committed_schema_matches_model(model: type, filename: str) -> None:
    path = _xtest_schema_dir() / filename
    assert path.is_file(), (
        f"Missing {path}. Run `uv run otdf-sdk-mgr schema dump` to regenerate."
    )
    expected = render(model)
    actual = path.read_text(encoding="utf-8")
    assert actual == expected, (
        f"{path} is out of sync with {model.__name__}. "
        f"Run `uv run otdf-sdk-mgr schema dump` to regenerate."
    )
