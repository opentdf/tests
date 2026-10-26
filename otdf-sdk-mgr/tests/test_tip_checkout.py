"""`install tip` checks each ref out into the directory make builds from.

cmd_tip runs make with `VERSIONS=<slug>`, and the SDK Makefiles build
`src/$VERSIONS` into `dist/$VERSIONS`. Only subprocesses are stubbed: every
git command succeeds and does nothing except `worktree add`, which creates the
worktree, and make records what it was told to build.
"""

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from otdf_sdk_mgr import installers

SHA = "0123456789abcdef0123456789abcdef01234567"

# Each ref and the dist/ directory make builds it into.
DIST_NAMES = {
    "main": "main",
    "feature/x": "feature--x",
    "sdk/v1.2.3": "v1.2.3",
    "otdfctl/v0.24.0": "v0.24.0",
    "refs/pull/123/head": "refs--pull--123--head",
    SHA: SHA,
}


def fake_git(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Stand-in for subprocess.run. `worktree add` creates the worktree, with
    the otdfctl/ subtree the go checkout requires."""
    assert cmd[0] == "git", cmd
    if cmd[2:4] == ["worktree", "add"]:
        (Path(cmd[-2]) / "otdfctl").mkdir(parents=True)
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


@pytest.mark.parametrize("ref", DIST_NAMES)
@pytest.mark.parametrize("sdk", ["go", "java", "js"])
def test_checks_out_where_make_builds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sdk: str, ref: str
):
    """A checkout under any other name leaves make with no `src/$VERSIONS`, or
    with a stale one left there by an earlier checkout, which it then builds."""
    monkeypatch.setenv("OTDF_SDK_DIR", str(tmp_path))
    envs: list[dict[str, str]] = []
    with (
        patch("otdf_sdk_mgr.checkout.subprocess.run", side_effect=fake_git),
        patch(
            "otdf_sdk_mgr.installers.subprocess.check_call",
            side_effect=lambda cmd, cwd, env: envs.append(env),
        ),
    ):
        installers.cmd_tip([sdk], ref=ref)

    [env] = envs
    assert env["VERSIONS"] == DIST_NAMES[ref]
    # What make would build without VERSIONS: everything in src/ but bare repos.
    src = tmp_path / sdk / "src"
    assert [p.name for p in src.iterdir() if not p.name.endswith(".git")] == [env["VERSIONS"]]
    if sdk == "go":
        worktree = tmp_path / "go" / "platform-src" / env["VERSIONS"]
        assert (src / env["VERSIONS"]).resolve() == (worktree / "otdfctl").resolve()
