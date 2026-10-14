"""Tests that a service dying on startup is reported rather than swallowed.

`go run ./service start` succeeds the instant `go` is on PATH, so a rejected
config key, a compile error, or a busy port all look like a healthy start until
the process exits a moment later. These tests pin the detection of that window;
they use a stub process manager so nothing here needs a Go toolchain.
"""

import subprocess
import sys
import time
from pathlib import Path

import pytest

from otdf_local.config.settings import Settings
from otdf_local.process.manager import ManagedProcess, ProcessManager
from otdf_local.services.kas import KASService

# Exits immediately with a distinctive, non-zero code.
DIES = [sys.executable, "-c", "raise SystemExit(3)"]
# Outlives any settle window the code under test uses.
SURVIVES = [sys.executable, "-c", "import time; time.sleep(30)"]


@pytest.fixture
def spawn():
    """Start a real subprocess as a ManagedProcess, killed on teardown."""
    started: list[ManagedProcess] = []

    def _spawn(cmd: list[str], log_file: Path | None = None) -> ManagedProcess:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        managed = ManagedProcess(name="test", process=proc, log_file=log_file)
        started.append(managed)
        return managed

    yield _spawn

    for managed in started:
        if managed.running:
            managed.process.kill()
            managed.process.wait()


class StubProcessManager(ProcessManager):
    """Hands back a ManagedProcess wrapping `cmd`, ignoring what it is asked to run.

    Lets the KASService tests exercise the real start() logic against a process
    whose exit behaviour they control.
    """

    def __init__(self, spawn, cmd: list[str]) -> None:
        super().__init__()
        self._spawn = spawn
        self._cmd = cmd

    def start(
        self,
        name: str,
        cmd: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        log_file: Path | None = None,
        pid_file: Path | None = None,
    ) -> ManagedProcess:
        return self._spawn(self._cmd, log_file)


def test_startup_error_is_none_while_process_runs(spawn):
    assert spawn(SURVIVES).startup_error(settle=0.3) is None


def test_startup_error_reports_exit_code_and_log_path(spawn, tmp_path):
    log_file = tmp_path / "kas-alpha.log"

    error = spawn(DIES, log_file).startup_error(settle=5)

    assert error is not None
    # The exit code and the log path are the two things that make the failure
    # actionable; without them the caller can only say "it didn't come up".
    assert "code 3" in error
    assert str(log_file) in error


def test_startup_error_omits_log_path_when_there_is_none(spawn):
    error = spawn(DIES).startup_error(settle=5)

    assert error is not None
    assert "see" not in error


def test_startup_error_returns_promptly_for_a_live_process(spawn):
    """The settle window is an upper bound on a healthy start, not a fixed sleep."""
    managed = spawn(SURVIVES)
    began = time.monotonic()
    managed.startup_error(settle=0.3)

    assert time.monotonic() - began < 2.0


def _kas_service(tmp_path, spawn, cmd, monkeypatch) -> KASService:
    settings = Settings(xtest_root=tmp_path, platform_dir=tmp_path)
    monkeypatch.setattr(
        "otdf_local.services.kas.kill_process_on_port", lambda port: None
    )
    kas = KASService(settings, "alpha", StubProcessManager(spawn, cmd))
    monkeypatch.setattr(kas, "_generate_config", lambda: tmp_path / "kas-alpha.yaml")
    return kas


def test_kas_start_reports_a_process_that_dies_immediately(
    tmp_path, spawn, monkeypatch
):
    kas = _kas_service(tmp_path, spawn, DIES, monkeypatch)

    assert kas.start() is False
    assert kas.start_error is not None
    assert "code 3" in kas.start_error


def test_kas_start_succeeds_for_a_process_that_stays_up(tmp_path, spawn, monkeypatch):
    kas = _kas_service(tmp_path, spawn, SURVIVES, monkeypatch)

    assert kas.start() is True
    assert kas.start_error is None


def test_kas_start_clears_a_stale_error_from_a_previous_attempt(
    tmp_path, spawn, monkeypatch
):
    kas = _kas_service(tmp_path, spawn, SURVIVES, monkeypatch)
    kas.start_error = "left over from an earlier failure"

    assert kas.start() is True
    assert kas.start_error is None


# A real failure, copied from a run where the compose file bind-mounted a file
# Docker could not chown. Compose reports progress on stderr too, so the line
# that matters is buried in noise -- which is how it came to be discarded.
COMPOSE_FAILURE_STDERR = """\
time="..." level=warning msg="The \\"JAVA_OPTS_APPEND\\" variable is not set."
 Container main-keycloak-1 Starting
 Container main-opentdfdb-1 Starting
 Container main-opentdfdb-1 Started
Error response from daemon: error while creating mount source path \
'/w/platform/keys/ca.jks': chown /w/platform/keys/ca.jks: permission denied
"""


def _docker_service(tmp_path: Path, monkeypatch, returncode: int, stderr: str):
    from otdf_local.services.docker import DockerService

    settings = Settings(xtest_root=tmp_path, platform_dir=tmp_path)
    (tmp_path / "docker-compose.yaml").write_text("services: {}\n")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout="", stderr=stderr
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    return DockerService(settings)


def test_docker_start_reports_why_compose_failed(tmp_path, monkeypatch):
    docker = _docker_service(tmp_path, monkeypatch, 1, COMPOSE_FAILURE_STDERR)

    assert docker.start() is False
    assert docker.start_error is not None
    # The daemon's reason, not just "it failed" -- this is the whole point.
    assert "permission denied" in docker.start_error
    # And not the progress chatter that surrounds it.
    assert "Starting" not in docker.start_error


def test_docker_start_reports_a_silent_nonzero_exit(tmp_path, monkeypatch):
    # No output at all still has to say something: an empty start_error reads
    # as success to `or`-style callers.
    docker = _docker_service(tmp_path, monkeypatch, 17, "")

    assert docker.start() is False
    assert docker.start_error is not None
    assert "17" in docker.start_error


def test_docker_start_names_a_missing_compose_file(tmp_path, monkeypatch):
    docker = _docker_service(tmp_path, monkeypatch, 0, "")
    docker._compose_file.unlink()

    assert docker.start() is False
    assert docker.start_error is not None
    assert "docker-compose.yaml" in docker.start_error


def test_docker_start_clears_a_stale_error(tmp_path, monkeypatch):
    docker = _docker_service(tmp_path, monkeypatch, 0, "")
    docker.start_error = "left over from an earlier failure"

    assert docker.start() is True
    assert docker.start_error is None
