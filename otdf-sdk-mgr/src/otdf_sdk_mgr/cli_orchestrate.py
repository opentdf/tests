"""`otdf-sdk-mgr orchestrate` subcommands.

Read a multi-repo feature spec from `xtest/features/<name>.yaml`, topologically
sort the cells by `depends_on`, create one git worktree per cell at
`~/Documents/GitHub/worktrees/<JIRA-KEY>-<cell-key>/`, and fan out `claude -p`
subagents to implement each cell in parallel within each wave. Each subagent
opens a draft PR and prints its URL as the last line of stdout.

The `tests` cell is skipped — `feature-design` already produced its artifacts
(scenario, draft test, `feature_type` entry).
"""

from __future__ import annotations

import concurrent.futures
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Iterable

import typer
from ruamel.yaml import YAML

orchestrate_app = typer.Typer(
    help="Fan out per-cell subagents to implement a multi-repo feature.",
)


# ------------------------------------------------------------------ data model


@dataclass(frozen=True)
class Cell:
    key: str
    path: str | None
    branch: str
    todo: tuple[str, ...]
    depends_on: tuple[str, ...]


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    jira: str | None
    title: str
    body: str
    cells: dict[str, Cell]
    scenarios: tuple[str, ...]


# ------------------------------------------------------------------ load


def _safe_yaml() -> YAML:
    return YAML(typ="safe")


def load_spec(path: Path) -> FeatureSpec:
    raw = path.read_text(encoding="utf-8")
    parsed = _safe_yaml().load(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: top-level must be a mapping")

    meta = parsed.get("metadata") or {}
    if not isinstance(meta, dict):
        raise ValueError(f"{path}: metadata must be a mapping")
    name = meta.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError(f"{path}: metadata.name is required")

    repos = parsed.get("repos") or {}
    if not isinstance(repos, dict):
        raise ValueError(f"{path}: repos must be a mapping")

    cells: dict[str, Cell] = {}
    for key, entry in repos.items():
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: repos.{key} must be a mapping")
        branch = entry.get("branch")
        if not isinstance(branch, str) or not branch:
            raise ValueError(f"{path}: repos.{key}.branch is required")
        todo = entry.get("todo") or []
        if not isinstance(todo, list):
            raise ValueError(f"{path}: repos.{key}.todo must be a list")
        deps = entry.get("depends_on") or []
        if not isinstance(deps, list):
            raise ValueError(f"{path}: repos.{key}.depends_on must be a list")
        repo_path = entry.get("path")
        if key != "tests" and not isinstance(repo_path, str):
            raise ValueError(
                f"{path}: repos.{key}.path is required for non-tests cells"
            )
        cells[key] = Cell(
            key=key,
            path=repo_path,
            branch=branch,
            todo=tuple(str(t) for t in todo),
            depends_on=tuple(str(d) for d in deps),
        )

    for cell in cells.values():
        for dep in cell.depends_on:
            if dep not in cells:
                raise ValueError(
                    f"{path}: repos.{cell.key}.depends_on references unknown key '{dep}'"
                )

    return FeatureSpec(
        name=name,
        jira=meta.get("jira"),
        title=meta.get("title", name),
        body=raw,
        cells=cells,
        scenarios=tuple(parsed.get("scenarios") or []),
    )


# ------------------------------------------------------------------ topo sort


def topological_waves(
    cells: dict[str, Cell], *, skip: Iterable[str] = ()
) -> list[list[Cell]]:
    """Group cells into dependency waves; cells within a wave are independent.

    Skipped cells are treated as already-done (their dependents see them as
    satisfied). Raises ValueError on cycles, naming the remaining set.
    """
    skip_set = set(skip)
    active = {k: c for k, c in cells.items() if k not in skip_set}

    indeg: dict[str, int] = {k: 0 for k in active}
    for cell in active.values():
        for dep in cell.depends_on:
            if dep in active:
                indeg[cell.key] += 1

    waves: list[list[Cell]] = []
    remaining = dict(active)
    while remaining:
        wave_keys = sorted(k for k, d in indeg.items() if d == 0 and k in remaining)
        if not wave_keys:
            raise ValueError(f"Dependency cycle among cells: {sorted(remaining)}")
        wave = [remaining[k] for k in wave_keys]
        waves.append(wave)
        for k in wave_keys:
            del remaining[k]
            for other in remaining.values():
                if k in other.depends_on:
                    indeg[other.key] -= 1
    return waves


# ------------------------------------------------------------------ worktrees


OPENTDF_ROOT = Path.home() / "Documents/GitHub/opentdf"
WORKTREES_ROOT = Path.home() / "Documents/GitHub/worktrees"


def worktree_for(spec: FeatureSpec, cell: Cell) -> Path:
    jira = spec.jira or spec.name
    return WORKTREES_ROOT / f"{jira}-{cell.key}"


def ensure_worktree(spec: FeatureSpec, cell: Cell) -> Path:
    """Create the cell's worktree if missing. Reuse if present and on the right branch.

    Bails (RuntimeError) if the directory exists but is on a different branch —
    we don't want to disturb concurrent work the user may have in flight.
    """
    if cell.path is None:
        raise ValueError(f"cell '{cell.key}' has no path; cannot create worktree")
    repo = OPENTDF_ROOT / cell.path
    if not repo.is_dir():
        raise FileNotFoundError(f"Sibling repo not found: {repo}")

    wt = worktree_for(spec, cell)
    if wt.exists():
        current = subprocess.check_output(
            ["git", "-C", str(wt), "branch", "--show-current"], text=True
        ).strip()
        if current != cell.branch:
            raise RuntimeError(
                f"Worktree {wt} is on branch '{current}', expected '{cell.branch}'. "
                f"Remove it manually or check it out to the right branch."
            )
        return wt

    wt.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        ["git", "-C", str(repo), "worktree", "add", str(wt), "-b", cell.branch],
    )
    return wt


# ----------------------------------------------------- subagent settings.json


COMMON_ALLOW: tuple[str, ...] = (
    "Bash(git *)",
    "Bash(gh pr create *)",
    "Bash(gh pr edit *)",
    "Bash(gh pr view *)",
    "Bash(ls *)",
    "Bash(cat *)",
    "Skill(*)",
)

REPO_ALLOW: dict[str, tuple[str, ...]] = {
    "platform": ("Bash(go *)", "Bash(make *)", "Bash(buf *)", "Bash(yq *)"),
    "java-sdk": ("Bash(mvn *)", "Bash(./mvnw *)"),
    "web-sdk": ("Bash(npm *)", "Bash(pnpm *)", "Bash(node *)"),
    "otdfctl": ("Bash(go *)", "Bash(make *)"),
}


def ensure_subagent_settings(worktree: Path, repo_path: str | None) -> None:
    """Pre-write a minimal .claude/settings.json so the subagent has a working allowlist.

    Skipped if the worktree already has one — the user may have committed a
    tighter or broader policy that we shouldn't overwrite.
    """
    settings_path = worktree / ".claude" / "settings.json"
    if settings_path.exists():
        return
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    allow = list(COMMON_ALLOW) + list(REPO_ALLOW.get(repo_path or "", ()))
    settings_path.write_text(
        json.dumps({"permissions": {"allow": allow}}, indent=2) + "\n",
        encoding="utf-8",
    )


# ----------------------------------------------------------- subagent prompt


PROMPT_TEMPLATE = """\
You are implementing a single cell of the OpenTDF feature `{name}` ({jira}).
Title: {title}
Branch (already checked out): {branch}
Cell key: {cell_key}
Working directory: a git worktree of the `{path}` repo.

The full feature spec is below for cross-cell context. Your work is whatever
`repos.{cell_key}.todo` lists.

--- BEGIN SPEC ---
{body}
--- END SPEC ---

Instructions:
1. Implement every item in `repos.{cell_key}.todo`. Don't switch branches.
2. Run the repo's local checks before committing (unit tests, linters, build).
3. Commit using house-style subject: `<type>({path}): <description> ({jira})`.
   No `Jira:` footer. Add `Co-Authored-By: Claude` to the message.
4. Open a draft PR via `gh pr create --draft --title "<same as commit subject>" --body "..."`.
   PR body references the parent Jira (https://virtru.atlassian.net/browse/{jira})
   and the tests-side scenario(s): {scenarios}.
5. Print the PR URL on the LAST LINE of your output — the orchestrator parses it.

Stay inside this worktree. Don't run pytest in tests/ — that's a different cell.
"""


def build_prompt(spec: FeatureSpec, cell: Cell) -> str:
    return PROMPT_TEMPLATE.format(
        name=spec.name,
        jira=spec.jira or "(no Jira ticket)",
        title=spec.title,
        branch=cell.branch,
        cell_key=cell.key,
        path=cell.path or "",
        body=spec.body,
        scenarios=", ".join(spec.scenarios) or "(none)",
    )


# ------------------------------------------------------------------ dispatch


PR_URL_RE = re.compile(r"https://github\.com/[^\s]+/pull/\d+")


@dataclass
class CellResult:
    cell: Cell
    worktree: Path
    transcript: Path
    success: bool
    pr_url: str | None
    error: str | None


def run_cell(
    spec: FeatureSpec,
    cell: Cell,
    *,
    transcripts_dir: Path,
    timeout_s: int,
    model: str,
) -> CellResult:
    try:
        wt = ensure_worktree(spec, cell)
    except Exception as e:
        return CellResult(cell, Path(), Path(), False, None, f"worktree: {e}")

    ensure_subagent_settings(wt, cell.path)

    transcripts_dir.mkdir(parents=True, exist_ok=True)
    transcript = transcripts_dir / f"{spec.jira or spec.name}-{cell.key}.jsonl"

    cmd = [
        "claude", "-p",
        "--model", model,
        "--permission-mode", "acceptEdits",
        "--output-format", "stream-json",
        "--verbose",
        build_prompt(spec, cell),
    ]
    try:
        with transcript.open("w", encoding="utf-8") as out:
            completed = subprocess.run(
                cmd,
                cwd=wt,
                stdout=out,
                stderr=subprocess.STDOUT,
                timeout=timeout_s,
            )
    except subprocess.TimeoutExpired:
        return CellResult(cell, wt, transcript, False, None, f"timed out after {timeout_s}s")

    if completed.returncode != 0:
        return CellResult(cell, wt, transcript, False, None, f"exit {completed.returncode}")

    pr_url: str | None = None
    for line in transcript.read_text(encoding="utf-8").splitlines():
        m = PR_URL_RE.search(line)
        if m:
            pr_url = m.group(0)
    return CellResult(cell, wt, transcript, True, pr_url, None)


# ---------------------------------------------------------------------- CLI


@orchestrate_app.command("run")
def run(
    spec_path: Annotated[Path, typer.Argument(help="Path to xtest/features/<name>.yaml")],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print the plan, don't dispatch.")
    ] = False,
    only: Annotated[
        list[str] | None,
        typer.Option("--only", help="Only run these cell keys (repeatable)."),
    ] = None,
    timeout_s: Annotated[
        int, typer.Option("--timeout", help="Per-cell timeout (seconds).")
    ] = 1800,
    model: Annotated[
        str, typer.Option("--model", help="Sub-agent model alias.")
    ] = "sonnet",
    transcripts_dir: Annotated[
        Path,
        typer.Option(
            "--transcripts-dir",
            help="Directory for per-cell JSONL transcripts.",
        ),
    ] = Path(".claude/tmp/runs"),
) -> None:
    """Fan out per-cell subagents for a multi-repo feature spec."""
    if not spec_path.is_file():
        typer.echo(f"Error: {spec_path} not found", err=True)
        raise typer.Exit(1)
    try:
        spec = load_spec(spec_path)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e

    skip: set[str] = {"tests"}
    if only:
        only_set = set(only)
        unknown = only_set - set(spec.cells)
        if unknown:
            typer.echo(f"Error: --only references unknown cell(s): {sorted(unknown)}", err=True)
            raise typer.Exit(1)
        skip = skip | (set(spec.cells) - only_set)

    try:
        waves = topological_waves(spec.cells, skip=skip)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e

    if dry_run:
        typer.echo(f"Feature: {spec.name} ({spec.jira or 'no Jira'}) — {spec.title}")
        for i, wave in enumerate(waves, 1):
            typer.echo(f"  Wave {i}:")
            for cell in wave:
                wt = worktree_for(spec, cell)
                typer.echo(
                    f"    - {cell.key}: path={cell.path} branch={cell.branch} worktree={wt}"
                )
        return

    failed: set[str] = set()
    results: list[CellResult] = []
    for i, wave in enumerate(waves, 1):
        typer.echo(f"=== Wave {i} ({len(wave)} cells) ===")
        runnable = [c for c in wave if not (set(c.depends_on) & failed)]
        for skipped in (c for c in wave if c not in runnable):
            typer.echo(f"  skipping {skipped.key}: upstream dependency failed")
            results.append(
                CellResult(skipped, Path(), Path(), False, None, "upstream dependency failed")
            )
            failed.add(skipped.key)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(runnable))) as ex:
            futures = {
                ex.submit(
                    run_cell,
                    spec,
                    c,
                    transcripts_dir=transcripts_dir,
                    timeout_s=timeout_s,
                    model=model,
                ): c
                for c in runnable
            }
            for fut in concurrent.futures.as_completed(futures):
                r = fut.result()
                results.append(r)
                status = "OK" if r.success else "FAIL"
                detail = r.pr_url or r.error or "(no PR URL)"
                typer.echo(f"  [{status}] {r.cell.key}: {detail}")
                if not r.success:
                    failed.add(r.cell.key)

    typer.echo("")
    typer.echo("=== Final report ===")
    typer.echo(f"{'CELL':<24} {'STATUS':<6} PR / ERROR")
    for r in results:
        status = "OK" if r.success else "FAIL"
        rhs = r.pr_url or r.error or "?"
        typer.echo(f"{r.cell.key:<24} {status:<6} {rhs}")

    if any(not r.success for r in results):
        raise typer.Exit(1)
