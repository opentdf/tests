"""Exercise the CI setup action when a Go release artifact install fails."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from ruamel.yaml import YAML


@pytest.mark.parametrize(
    ("tag", "release", "source", "repo", "source_dir", "is_platform"),
    [
        ("v0.24.0", "v0.24.0", "otdfctl", "opentdf/otdfctl", "src", "false"),
        (
            "v0.41.0",
            "otdfctl/v0.41.0",
            "platform",
            "opentdf/platform",
            "platform-src",
            "true",
        ),
    ],
)
def test_failed_go_release_install_checks_out_its_source_repository(
    tmp_path: Path,
    tag: str,
    release: str,
    source: str,
    repo: str,
    source_dir: str,
    is_platform: str,
) -> None:
    if shutil.which("jq") is None:
        pytest.skip("setup-cli-tool requires jq")

    action_path = Path(__file__).resolve().parents[2] / "xtest/setup-cli-tool/action.yaml"
    action = YAML(typ="safe").load(action_path.read_text())
    steps = action["runs"]["steps"]
    scripts = {step.get("id", step["name"]): step["run"] for step in steps if "run" in step}

    sdk_path = tmp_path / "workspace/xtest/sdk"
    sdk_path.mkdir(parents=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text("#!/bin/sh\nexit 1\n")
    fake_uv.chmod(0o755)

    github_env = tmp_path / "github-env"
    github_output = tmp_path / "github-output"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "INPUT_PATH": str(sdk_path),
            "INPUT_SDK": "go",
            "GITHUB_ENV": str(github_env),
            "GITHUB_OUTPUT": str(github_output),
            "PLATFORM_OTDFCTL_DIR": "",
            "PLATFORM_OTDFCTL_SHA": "",
            "version_info": json.dumps(
                [{"tag": tag, "sha": "a" * 40, "release": release, "source": source}]
            ),
        }
    )

    for script in (
        scripts["identify repo urls"],
        scripts["resolve"],
        scripts["install released versions"],
        scripts["check-source"],
    ):
        subprocess.run(["bash", "-e", "-o", "pipefail", "-c", script], env=env, check=True)
        if github_env.exists():
            env.update(dict(line.split("=", 1) for line in github_env.read_text().splitlines()))

    output = dict(line.split("=", 1) for line in github_output.read_text().splitlines())
    assert env[f"BUILD_FROM_SOURCE_{tag.replace('.', '_')}"] == "true"
    assert output["selected-tag"] == tag
    assert output["needs-build"] == "true"
    assert output["needs-checkout-a"] == "true"
    assert output["is-platform-a"] == is_platform
    assert output["checkout-repo-a"] == repo
    assert output["checkout-path-a"] == str(sdk_path / "go" / source_dir / tag)
