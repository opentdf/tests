"""Pytest configuration and core fixtures for OpenTDF integration tests.

This module contains:
- Pytest CLI options and test parametrization logic
- Core fixtures (test files, temp directories, otdfctl)
- Helper functions for test configuration

Domain-specific fixtures are organized in the fixtures/ package:
- fixtures.kas: KAS registry and KAS entry fixtures
- fixtures.attributes: Attribute and ABAC fixtures
- fixtures.assertions: TDF assertion fixtures
- fixtures.obligations: Obligation and trigger fixtures
- fixtures.keys: Key management fixtures
"""

import json
import logging
import os
import typing
from pathlib import Path
from typing import cast

import pytest

import tdfs
from otdfctl import OpentdfCommandLineTool

logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))

# Load all fixture modules
pytest_plugins = [
    "fixtures.kas",
    "fixtures.attributes",
    "fixtures.assertions",
    "fixtures.obligations",
    "fixtures.keys",
    "fixtures.audit",
]


def englist(s: tuple[str]) -> str:
    """Convert tuple of strings to English list format (e.g., 'a, b, or c')."""
    if len(s) > 1:
        return ", ".join(s[:-1]) + ", or " + s[-1]
    elif s:
        return s[0]
    return ""


def is_type_or_list_of_types(t: typing.Any) -> typing.Callable[[str], typing.Any]:
    """Create a validator function for CLI options that accept one or more typed values."""

    def is_a(v: str) -> typing.Any:
        for i in v.split():
            if i not in typing.get_args(t):
                raise ValueError(f"Invalid value for {t}: {i}")
        return v

    return is_a


def pytest_addoption(parser: pytest.Parser):
    """Add custom CLI options for pytest."""
    parser.addoption(
        "--audit-log-dir",
        help="directory to write audit logs on test failure (default: tmp/audit-logs)",
        type=Path,
    )
    parser.addoption(
        "--audit-log-services",
        help="comma-separated list of docker compose services to monitor for audit logs",
        type=list[str],
    )
    parser.addoption(
        "--containers",
        help=f"which container formats to test, one or more of {englist(typing.get_args(tdfs.container_type))}",
        type=is_type_or_list_of_types(tdfs.container_type),
    )
    parser.addoption(
        "--focus",
        help="skips tests which don't use the requested sdk",
        type=is_type_or_list_of_types(tdfs.focus_type),
    )
    parser.addoption(
        "--large",
        action="store_true",
        help="generate a large (greater than 4 GiB) file for testing",
    )
    parser.addoption(
        "--no-audit-logs",
        action="store_true",
        help="disable automatic KAS audit log collection",
    )
    parser.addoption(
        "--sdks",
        help=f"select which sdks to run by default, unless overridden, one or more of {englist(typing.get_args(tdfs.sdk_type))}",
        type=is_type_or_list_of_types(tdfs.sdk_type),
    )
    parser.addoption(
        "--sdks-decrypt",
        help="select which sdks to run for decrypt only",
        type=is_type_or_list_of_types(tdfs.sdk_type),
    )
    parser.addoption(
        "--sdks-encrypt",
        help="select which sdks to run for encrypt only",
        type=is_type_or_list_of_types(tdfs.sdk_type),
    )


def pytest_generate_tests(metafunc: pytest.Metafunc):
    """Dynamically parametrize test functions based on CLI options.

    This hook parametrizes fixtures based on command-line options:
    - size: large or small test files
    - encrypt_sdk: which SDK(s) to use for encryption
    - decrypt_sdk: which SDK(s) to use for decryption
    - in_focus: filter tests by SDK focus
    - container: which container formats to test (ztdf, nano)
    """
    if "size" in metafunc.fixturenames:
        metafunc.parametrize(
            "size",
            ["large" if metafunc.config.getoption("large") else "small"],
            scope="session",
        )

    def list_opt(name: str, t: typing.Any) -> list[str]:
        ttt = typing.get_args(t)
        v = metafunc.config.getoption(name)
        if not v:
            return []
        if type(v) is not str:
            raise ValueError(f"Invalid value for {name}: {v}")
        a = v.split()
        for i in a:
            if i not in ttt:
                raise ValueError(f"Invalid value for {name}: {i}, must be one of {ttt}")
        return a

    def defaulted_list_opt[T](
        names: list[str], t: typing.Any, default: list[T]
    ) -> list[T]:
        for name in names:
            v = metafunc.config.getoption(name)
            if v:
                return cast(list[T], list_opt(name, t))
        return default

    subject_sdks: set[tdfs.SDK] = set()

    if "encrypt_sdk" in metafunc.fixturenames:
        encrypt_sdks: list[tdfs.sdk_type] = []
        encrypt_sdks = defaulted_list_opt(
            ["--sdks-encrypt", "--sdks"],
            tdfs.sdk_type,
            list(typing.get_args(tdfs.sdk_type)),
        )
        # convert list of sdk_type to list of SDK objects
        e_sdks = [
            v
            for sdks in [tdfs.all_versions_of(sdk) for sdk in encrypt_sdks]
            for v in sdks
        ]
        metafunc.parametrize("encrypt_sdk", e_sdks, ids=[str(x) for x in e_sdks])
        subject_sdks |= set(e_sdks)
    if "decrypt_sdk" in metafunc.fixturenames:
        decrypt_sdks: list[tdfs.sdk_type] = []
        decrypt_sdks = defaulted_list_opt(
            ["--sdks-decrypt", "--sdks"],
            tdfs.sdk_type,
            list(typing.get_args(tdfs.sdk_type)),
        )
        d_sdks = [
            v
            for sdks in [tdfs.all_versions_of(sdk) for sdk in decrypt_sdks]
            for v in sdks
        ]
        metafunc.parametrize("decrypt_sdk", d_sdks, ids=[str(x) for x in d_sdks])
        subject_sdks |= set(d_sdks)

    if "in_focus" in metafunc.fixturenames:
        focus_opt = "all"
        if metafunc.config.getoption("--focus"):
            focus_opt = metafunc.config.getoption("--focus")
        focus: set[tdfs.sdk_type] = set()
        if focus_opt == "all":
            focus = set(typing.get_args(tdfs.sdk_type))
        else:
            focus = cast(set[tdfs.sdk_type], set(list_opt("--focus", tdfs.focus_type)))
        focused_sdks = {s for s in subject_sdks if s.sdk in focus}
        metafunc.parametrize("in_focus", [focused_sdks])

    if "container" in metafunc.fixturenames:
        containers: list[tdfs.container_type] = []
        if metafunc.config.getoption("--containers"):
            containers = cast(
                list[tdfs.container_type], list_opt("--containers", tdfs.container_type)
            )
        else:
            containers = list(typing.get_args(tdfs.container_type))
        metafunc.parametrize("container", containers)


# Core fixtures
@pytest.fixture(scope="module")
def pt_file(tmp_dir: Path, size: str) -> Path:
    """Generate a plaintext test file.

    Args:
        tmp_dir: Temporary directory for test files
        size: 'large' (>4 GiB) or 'small' (128 bytes)

    Returns:
        Path to the generated plaintext file
    """
    pt_file = tmp_dir / f"test-plain-{size}.txt"
    length = (5 * 2**30) if size == "large" else 128
    with pt_file.open("w") as f:
        for i in range(0, length, 16):
            f.write(f"{i:15,d}\n")
    return pt_file


@pytest.fixture(scope="package")
def tmp_dir(request: pytest.FixtureRequest) -> Path:
    """Create worker-specific temporary directory for test files.

    When running with pytest-xdist, each worker gets its own subdirectory
    to prevent file collisions between parallel test processes.
    """
    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    dname = Path(f"tmp/{worker_id}/")
    dname.mkdir(parents=True, exist_ok=True)
    return dname


def load_otdfctl() -> OpentdfCommandLineTool:
    """Load the otdfctl CLI tool from the SDK distribution.

    Attempts to load otdfctl in this order:
    1. First head version from OTDFCTL_HEADS environment variable
    2. Main branch version (sdk/go/dist/main/otdfctl.sh)
    3. System-installed otdfctl

    Returns:
        OpentdfCommandLineTool instance configured for the available otdfctl
    """
    oh = os.environ.get("OTDFCTL_HEADS", "[]")
    try:
        heads = json.loads(oh)
        if heads:
            return OpentdfCommandLineTool(f"sdk/go/dist/{heads[0]}/otdfctl.sh")
    except json.JSONDecodeError:
        print(f"Invalid OTDFCTL_HEADS environment variable: [{oh}]")
    if os.path.isfile("sdk/go/dist/main/otdfctl.sh"):
        return OpentdfCommandLineTool("sdk/go/dist/main/otdfctl.sh")
    return OpentdfCommandLineTool()


_otdfctl = load_otdfctl()


@pytest.fixture(scope="module")
def otdfctl():
    """Provide access to the otdfctl CLI tool."""
    return _otdfctl
