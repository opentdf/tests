"""The ``cli.sh validate <file>`` contract, and running it.

Every SDK's shim passes its CLI's stdout and exit status through unchanged:

- exit 0, stdout ``{"valid":true}``: the file is a valid TDF;
- exit 3, stdout ``{"valid":false,"reason":"..."}``: the check ran and the
  file is not a valid TDF;
- anything else -- another exit status, a signal, a timeout, or stdout that
  is not exactly one such JSON line -- means the check could not run.

Not exit 1 for "invalid": cobra, Node and picocli all exit 1 on an unhandled
error (and picocli 2 on a usage error), so a crash would read as a verdict.
"""

import json
import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import tdfs

#: Exit status of a CLI whose check completed and found the file valid.
EXIT_VALID = 0
#: Exit status of a CLI whose check completed and found the file invalid.
EXIT_INVALID = 3

#: Seconds one ``validate`` may take. Generous: the slowest honest answer is a
#: cold JVM reading an 11 MiB manifest, which is well under this. A reader
#: that hangs on a malformed archive is what it is there to catch.
TIMEOUT = float(os.environ.get("XT_VALIDATE_TIMEOUT", "60"))

Outcome = Literal["valid", "invalid", "error"]

#: How much of a reason or diagnostic to keep. Go's schema failures list
#: every violation, and a report nobody can read is not a report.
_KEEP = 400


@dataclass(frozen=True, slots=True)
class ValidateResult:
    """What one ``cli.sh validate`` run said, classified."""

    outcome: Outcome
    #: For ``invalid``, the CLI's reason. For ``error``, what went wrong.
    reason: str = ""
    #: The tail of stderr, kept for diagnosing an ``error``.
    stderr: str = ""


def _head(text: str, n: int = _KEEP) -> str:
    """The start of a reason: where every SDK says which layer rejected it."""
    text = text.strip()
    return text if len(text) <= n else text[:n] + "..."


def _tail(raw: bytes | str, n: int = _KEEP) -> str:
    """The end of stderr: where a stack trace says what actually failed."""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    text = text.strip()
    return text if len(text) <= n else "..." + text[-n:]


def parse_output(returncode: int, stdout: bytes, stderr: bytes = b"") -> ValidateResult:
    """Classify one finished ``validate`` process against the contract.

    Strict on purpose. Exit 0 or 3 is a verdict only if stdout agrees with it,
    as exactly one JSON object; anything else is reported as an ``error``
    naming the violation, because a shim or CLI that has drifted from the
    contract is not answering the question this suite asks.
    """
    err = _tail(stderr)

    def error(why: str) -> ValidateResult:
        return ValidateResult("error", why, err)

    if returncode < 0:
        try:
            name = signal.Signals(-returncode).name
        except ValueError:
            name = f"signal {-returncode}"
        return error(f"killed by {name}")
    if returncode not in (EXIT_VALID, EXIT_INVALID):
        return error(f"exit {returncode}: the check could not run")

    text = stdout.decode("utf-8", errors="replace").strip()
    shown = repr(_tail(text, 200))
    lines = text.splitlines()
    if len(lines) != 1:
        return error(
            f"exit {returncode} but stdout has {len(lines)} lines, not one JSON "
            f"line: {shown}"
        )
    try:
        record = json.loads(lines[0])
    except json.JSONDecodeError:
        return error(f"exit {returncode} but stdout is not JSON: {shown}")
    if not isinstance(record, dict) or not isinstance(record.get("valid"), bool):
        return error(f'exit {returncode} but stdout has no boolean "valid": {shown}')
    record = cast(dict[str, Any], record)
    valid: bool = record["valid"]
    if valid != (returncode == EXIT_VALID):
        return error(
            f'exit {returncode} contradicts stdout "valid":{json.dumps(valid)}'
        )
    if valid:
        return ValidateResult("valid", "", err)
    reason = record.get("reason", "")
    if not isinstance(reason, str):
        return error(f'"reason" is not a string: {reason!r}')
    return ValidateResult("invalid", _head(reason), err)


def validate(
    sdk: tdfs.SDK, tdf_file: Path, *, timeout: float = TIMEOUT
) -> ValidateResult:
    """Ask ``sdk``'s CLI whether ``tdf_file`` is a valid TDF.

    Never raises for the CLI's sake: a crash, a hang or output outside the
    contract comes back as an ``error`` result, so the caller can hold it to
    the baseline like any other answer. Needs no platform. Every shim
    ``exec``\\s its CLI, so killing the child on timeout kills the reader.
    """
    try:
        run = subprocess.run(
            [sdk.path, "validate", str(tdf_file)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return ValidateResult(
            "error", f"timed out after {timeout}s", _tail(e.stderr or b"")
        )
    return parse_output(run.returncode, run.stdout, run.stderr)
