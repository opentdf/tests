"""`otdf-sdk-mgr schema` subcommands.

Emit canonical JSON Schemas for the Pydantic models in `otdf_sdk_mgr.schema`
so agents (and humans) can introspect the on-disk YAML formats without
running `python -c` against the package. The generated files live under
`xtest/schema/` and are kept in sync via `tests/test_schema_sync.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from otdf_sdk_mgr.schema import Instance, Scenario

schema_app = typer.Typer(help="Emit JSON Schemas for the scenario/instance models.")

# (model_class, output_filename). Add new models here and `schema dump`
# will pick them up automatically.
SCHEMAS: tuple[tuple[type, str], ...] = (
    (Scenario, "scenario.schema.json"),
    (Instance, "instance.schema.json"),
)


def render(model: type) -> str:
    """Render `model.model_json_schema()` as a deterministic JSON string.

    Sorted keys and a trailing newline so byte-equality comparisons in the
    sync test are stable.
    """
    return json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"


@schema_app.command("dump")
def dump(
    out_dir: Annotated[
        Path,
        typer.Option(
            "--out-dir",
            help="Directory to write *.schema.json files into.",
        ),
    ] = Path("xtest/schema"),
) -> None:
    """Write JSON Schemas for every canonical scenario/instance model.

    Overwrites existing files. Re-run whenever a Pydantic model changes;
    the committed schemas in xtest/schema/ are otherwise the source of
    truth that the scenario-authoring skills read.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for model, filename in SCHEMAS:
        path = out_dir / filename
        path.write_text(render(model), encoding="utf-8")
        typer.echo(f"  wrote {path}")
