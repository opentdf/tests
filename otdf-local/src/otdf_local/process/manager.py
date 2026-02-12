"""Subprocess lifecycle management."""

import os
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO


@dataclass
class ManagedProcess:
    """A managed subprocess with metadata."""

    name: str
    process: subprocess.Popen
    log_file: Path | None = None
    pid_file: Path | None = None
    _log_handle: IO | None = field(default=None, repr=False)

    @property
    def pid(self) -> int:
        """Process ID."""
        return self.process.pid

    @property
    def running(self) -> bool:
        """Check if process is still running."""
        return self.process.poll() is None

    @property
    def return_code(self) -> int | None:
        """Return code if process has exited."""
        return self.process.poll()

    def stop(self, timeout: float = 10.0) -> int | None:
        """Stop the process gracefully, then forcefully if needed.

        Args:
            timeout: Seconds to wait for graceful shutdown

        Returns:
            Process return code
        """
        if not self.running:
            return self.return_code

        # Try graceful shutdown first
        self.process.terminate()
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Force kill
            self.process.kill()
            self.process.wait(timeout=5)

        # Clean up PID file
        if self.pid_file and self.pid_file.exists():
            self.pid_file.unlink()

        # Close log handle
        if self._log_handle:
            self._log_handle.close()

        return self.return_code

    def kill(self) -> None:
        """Forcefully kill the process."""
        if self.running:
            self.process.kill()
            self.process.wait()

        if self.pid_file and self.pid_file.exists():
            self.pid_file.unlink()

        if self._log_handle:
            self._log_handle.close()


class ProcessManager:
    """Manages multiple subprocesses."""

    def __init__(self) -> None:
        self._processes: dict[str, ManagedProcess] = {}

    def start(
        self,
        name: str,
        cmd: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        log_file: Path | None = None,
        pid_file: Path | None = None,
    ) -> ManagedProcess:
        """Start a new managed process.

        Args:
            name: Unique name for this process
            cmd: Command and arguments
            cwd: Working directory
            env: Additional environment variables
            log_file: File to redirect stdout/stderr to
            pid_file: File to write PID to

        Returns:
            ManagedProcess instance
        """
        # Stop existing process with same name
        if name in self._processes:
            self._processes[name].stop()

        # Prepare environment
        process_env = os.environ.copy()
        if env:
            process_env.update(env)

        # Open log file if specified
        log_handle = None
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_handle = open(log_file, "w")

        # Start process
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=process_env,
            stdout=log_handle or subprocess.DEVNULL,
            stderr=subprocess.STDOUT if log_handle else subprocess.DEVNULL,
            start_new_session=True,  # Detach from parent
        )

        # Write PID file
        if pid_file:
            pid_file.parent.mkdir(parents=True, exist_ok=True)
            pid_file.write_text(str(process.pid))

        managed = ManagedProcess(
            name=name,
            process=process,
            log_file=log_file,
            pid_file=pid_file,
            _log_handle=log_handle,
        )
        self._processes[name] = managed
        return managed

    def get(self, name: str) -> ManagedProcess | None:
        """Get a managed process by name."""
        return self._processes.get(name)

    def stop(self, name: str, timeout: float = 10.0) -> int | None:
        """Stop a process by name.

        Returns:
            Process return code, or None if not found
        """
        if name not in self._processes:
            return None
        result = self._processes[name].stop(timeout)
        del self._processes[name]
        return result

    def stop_all(self, timeout: float = 10.0) -> None:
        """Stop all managed processes."""
        for name in list(self._processes.keys()):
            self.stop(name, timeout)

    def running(self) -> list[str]:
        """Get names of all running processes."""
        return [name for name, proc in self._processes.items() if proc.running]

    def __contains__(self, name: str) -> bool:
        return name in self._processes


def kill_process_on_port(port: int) -> bool:
    """Kill any process listening on the specified port.

    Args:
        port: Port number

    Returns:
        True if a process was killed
    """
    try:
        # Use lsof to find process on port
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return False

        pids = result.stdout.strip().split("\n")
        for pid in pids:
            try:
                os.kill(int(pid), signal.SIGKILL)
            except (ProcessLookupError, ValueError):
                pass
        return True
    except FileNotFoundError:
        # lsof not available
        return False


def find_pid_by_name(pattern: str) -> list[int]:
    """Find process IDs matching a pattern.

    Args:
        pattern: Pattern to match against process command line

    Returns:
        List of matching PIDs
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        return [int(pid) for pid in result.stdout.strip().split("\n")]
    except (FileNotFoundError, ValueError):
        return []
