"""Log file management and aggregation."""

import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class LogEntry:
    """A single log entry."""

    timestamp: datetime | None
    service: str
    message: str
    raw: str


class LogReader:
    """Read and tail log files."""

    def __init__(self, log_file: Path, service_name: str) -> None:
        self.log_file = log_file
        self.service_name = service_name
        self._position = 0

    def read_all(self) -> list[LogEntry]:
        """Read all lines from the log file."""
        if not self.log_file.exists():
            return []

        entries = []
        with open(self.log_file) as f:
            for line in f:
                entries.append(self._parse_line(line))
        return entries

    def read_tail(self, n: int = 50) -> list[LogEntry]:
        """Read the last n lines from the log file."""
        if not self.log_file.exists():
            return []

        # Simple tail implementation
        with open(self.log_file) as f:
            lines = f.readlines()

        return [self._parse_line(line) for line in lines[-n:]]

    def read_new(self) -> list[LogEntry]:
        """Read new lines since last read."""
        if not self.log_file.exists():
            return []

        entries = []
        with open(self.log_file) as f:
            f.seek(self._position)
            for line in f:
                entries.append(self._parse_line(line))
            self._position = f.tell()
        return entries

    def follow(self, poll_interval: float = 0.5) -> Iterator[LogEntry]:
        """Continuously yield new log entries."""
        while True:
            entries = self.read_new()
            yield from entries
            if not entries:
                time.sleep(poll_interval)

    def _parse_line(self, line: str) -> LogEntry:
        """Parse a log line to extract timestamp and message."""
        line = line.rstrip("\n")

        # Try to parse common timestamp formats
        timestamp = None

        # ISO format: 2024-01-15T10:30:45.123Z
        iso_match = re.match(
            r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s*(.*)",
            line,
        )
        if iso_match:
            try:
                ts_str = iso_match.group(1).rstrip("Z")
                timestamp = datetime.fromisoformat(ts_str)
                line = iso_match.group(2)
            except ValueError:
                pass

        # Standard format: 2024/01/15 10:30:45
        std_match = re.match(
            r"(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\s*(.*)",
            line,
        )
        if std_match and timestamp is None:
            try:
                timestamp = datetime.strptime(std_match.group(1), "%Y/%m/%d %H:%M:%S")
                line = std_match.group(2)
            except ValueError:
                pass

        return LogEntry(
            timestamp=timestamp,
            service=self.service_name,
            message=line,
            raw=line,
        )


class LogAggregator:
    """Aggregate logs from multiple services."""

    def __init__(self, logs_dir: Path) -> None:
        self.logs_dir = logs_dir
        self._readers: dict[str, LogReader] = {}

    def add_service(self, name: str, log_file: Path | None = None) -> None:
        """Add a service to aggregate logs from."""
        if log_file is None:
            log_file = self.logs_dir / f"{name}.log"
        self._readers[name] = LogReader(log_file, name)

    def read_all(
        self,
        services: list[str] | None = None,
        pattern: str | None = None,
    ) -> list[LogEntry]:
        """Read all logs, optionally filtered.

        Args:
            services: Service names to include (None = all)
            pattern: Regex pattern to filter messages

        Returns:
            List of log entries, sorted by timestamp
        """
        readers = self._get_readers(services)
        entries = []
        for reader in readers:
            entries.extend(reader.read_all())

        if pattern:
            regex = re.compile(pattern, re.IGNORECASE)
            entries = [e for e in entries if regex.search(e.message)]

        # Sort by timestamp, putting None timestamps last
        return sorted(
            entries,
            key=lambda e: (e.timestamp is None, e.timestamp or datetime.max),
        )

    def read_tail(
        self,
        n: int = 50,
        services: list[str] | None = None,
        pattern: str | None = None,
    ) -> list[LogEntry]:
        """Read last n lines from each service.

        Args:
            n: Number of lines per service
            services: Service names to include (None = all)
            pattern: Regex pattern to filter messages

        Returns:
            List of log entries, sorted by timestamp
        """
        readers = self._get_readers(services)
        entries = []
        for reader in readers:
            entries.extend(reader.read_tail(n))

        if pattern:
            regex = re.compile(pattern, re.IGNORECASE)
            entries = [e for e in entries if regex.search(e.message)]

        return sorted(
            entries,
            key=lambda e: (e.timestamp is None, e.timestamp or datetime.max),
        )

    def follow(
        self,
        services: list[str] | None = None,
        poll_interval: float = 0.5,
    ) -> Iterator[LogEntry]:
        """Continuously yield new log entries from all services."""
        readers = self._get_readers(services)

        while True:
            found_any = False
            for reader in readers:
                for entry in reader.read_new():
                    found_any = True
                    yield entry

            if not found_any:
                time.sleep(poll_interval)

    def _get_readers(self, services: list[str] | None) -> list[LogReader]:
        """Get readers for specified services."""
        if services is None:
            return list(self._readers.values())
        return [self._readers[s] for s in services if s in self._readers]
