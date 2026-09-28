"""The one adapter A1 ships: build the old argv, set the old env, exec the old shim.

Behaviour-identical by construction. Every ``XT_WITH_*`` name, every
positional slot and every "set this variable only when the value is truthy"
rule is transcribed unchanged from the callers this replaces, because the
point of the step is to move the seam without moving the behaviour. The
characterization suite pins that: it asserts the exact argv list and the exact
env dict, so a transcription slip is a failing assertion rather than a
mysteriously different run three PRs later.

Two consequences worth stating plainly, since they look like defects in this
file and are not:

* ``EncryptRequest.policy_mode`` and ``ecdsa_binding`` are accepted and
  ignored. The shims read ``XT_WITH_PLAINTEXT_POLICY`` and
  ``XT_WITH_ECDSA_BINDING``, but nothing in the harness has ever set either
  through this path, and inventing the mapping here would be a behaviour
  change smuggled into a refactor. The native adapters wire them up.
* ``DecryptRequest.kas_allowlist`` emits ``XT_WITH_KAS_ALLOWLIST``. All three
  shims read ``XT_WITH_KAS_ALLOW_LIST``. That mismatch is real and predates
  this package -- see the module's ``KNOWN_SHIM_MISMATCH`` note below.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

from otdf_adapter.descriptor import SHIM_NAME, AdapterDescriptor
from otdf_adapter.gates import GateResult, evaluate, lookup
from otdf_adapter.protocol import (
    DEFAULT_CONTAINER,
    AdapterError,
    DecryptRequest,
    EncryptRequest,
    SdkVersion,
)

logger = logging.getLogger("xtest")

#: Default root for installed builds, relative to the working directory.
#: Unchanged from ``sdk/<name>/dist/<version>/`` on purpose -- relocating it is
#: a separate concern and a separate ticket.
DEFAULT_SDK_DIR = Path("sdk")

#: ``kas_allowlist`` sets ``XT_WITH_KAS_ALLOWLIST``; all three shims read
#: ``XT_WITH_KAS_ALLOW_LIST``. So the option has never reached any SDK, and the
#: only caller that exercises it is the unit test that pins the env dict --
#: which passes, because it asserts the name the builder emits.
#:
#: Preserved verbatim here rather than fixed: this package is the
#: behaviour-identical step, and quietly starting to pass ``--kas-allowlist``
#: to three SDKs for the first time is not behaviour-identical. Fixing it
#: belongs with the native adapters, which build the flag directly and make
#: the variable moot.
KNOWN_SHIM_MISMATCH = {"XT_WITH_KAS_ALLOWLIST": "XT_WITH_KAS_ALLOW_LIST"}


class Command(NamedTuple):
    """An argv and the environment overrides it needs.

    A named 2-tuple, so ``argv, env = adapter.encrypt_command(req)`` keeps
    working for callers that only want the pair, and equality still compares
    both halves -- which is what makes the determinism check meaningful.

    ``env`` holds *only* the overrides. Merge it over ``os.environ`` before
    handing it to a subprocess.
    """

    argv: list[str]
    env: dict[str, str]


class SubprocessCliAdapter:
    """Drives ``sdk/<name>/dist/<version>/cli.sh``.

    Satisfies :class:`~otdf_adapter.protocol.SdkAdapter`. Registered under
    every built-in name in the ``otdf.adapters`` entry-point group, because
    for now every SDK is reached the same way.
    """

    def __init__(
        self,
        name: str,
        version: str = "main",
        dist_dir: Path | None = None,
        sdk_dir: Path | None = None,
        *,
        require_executable: bool = True,
    ) -> None:
        self.name = name
        self.version_spec = version
        root = Path(sdk_dir) if sdk_dir is not None else DEFAULT_SDK_DIR
        self.dist_dir = Path(dist_dir) if dist_dir is not None else root / name / "dist" / version
        self.descriptor = AdapterDescriptor.load(self.dist_dir, sdk=name, version=version)
        # A plain string, not a Path: it is spliced into argv and compared
        # against by callers, and ``str(Path("sdk/go/dist/main/cli.sh"))``
        # already differs from the literal on Windows.
        self.path = str(self.dist_dir / SHIM_NAME)
        if require_executable and not os.path.isfile(self.path):
            raise FileNotFoundError(f"SDK executable not found at path: {self.path}")
        self._version: SdkVersion | None = None
        self._help: dict[tuple[str, ...], str] = {}

    def __repr__(self) -> str:
        return f"SubprocessCliAdapter(name={self.name!r}, version={self.version_spec!r})"

    def __str__(self) -> str:
        return f"{self.name}@{self.version_spec}"

    # -- command builders -------------------------------------------------
    #
    # Pure: no filesystem, no subprocess, no shared state. The benchmark
    # harness builds a command once and runs it many times, so a builder that
    # mutated anything would make round N differ from round 1 and surface as a
    # phantom regression rather than as a bug here.

    def encrypt_command(self, request: EncryptRequest) -> Command:
        """The argv and ``XT_WITH_*`` overrides for one encrypt."""
        argv = [
            self.path,
            "encrypt",
            str(request.src),
            str(request.dst),
            request.container,
        ]

        env: dict[str, str] = {}
        if request.mime_type:
            env |= {"XT_WITH_MIME_TYPE": request.mime_type}

        if request.attributes:
            env |= {"XT_WITH_ATTRIBUTES": ",".join(request.attributes)}

        if request.assertions:
            env |= {"XT_WITH_ASSERTIONS": request.assertions}

        # Target mode is a ztdf-schema concept; asking for it against another
        # container would be silently ignored by the shim, so do not send it.
        if request.container == DEFAULT_CONTAINER and request.target_mode:
            env |= {"XT_WITH_TARGET_MODE": request.target_mode}

        if request.ecwrap:
            env |= {"XT_WITH_ECWRAP": "true"}
        return Command(argv, env)

    def decrypt_command(self, request: DecryptRequest) -> Command:
        """The argv and ``XT_WITH_*`` overrides for one decrypt."""
        argv = [
            self.path,
            "decrypt",
            str(request.src),
            str(request.dst),
            request.container,
        ]

        env: dict[str, str] = {}
        if request.assertion_verification_keys:
            env |= {"XT_WITH_ASSERTION_VERIFICATION_KEYS": request.assertion_verification_keys}
        if request.ecwrap:
            env |= {"XT_WITH_ECWRAP": "true"}
        if not request.verify_assertions:
            env |= {"XT_WITH_VERIFY_ASSERTIONS": "false"}
        if request.kas_allowlist:
            env |= {"XT_WITH_KAS_ALLOWLIST": request.kas_allowlist}
        if request.ignore_kas_allowlist:
            env |= {"XT_WITH_IGNORE_KAS_ALLOWLIST": "true"}
        return Command(argv, env)

    def supports_command(self, feature: str) -> Command:
        """The argv for the shim's ``supports`` verb. No env overrides."""
        return Command([self.path, "supports", feature], {})

    # -- execution --------------------------------------------------------

    def encrypt(self, request: EncryptRequest) -> Path:
        argv, env = self.encrypt_command(request)
        logger.debug("enc [%s]", " ".join([fmt_env(env), *argv]))
        self._run(argv, env, label="enc")
        return request.dst

    def decrypt(self, request: DecryptRequest) -> Path:
        argv, env = self.decrypt_command(request)
        logger.info("dec [%s]", " ".join([fmt_env(env), *argv]))
        self._run(argv, env, label="dec")
        return request.dst

    def supports(self, feature: str, container: str = DEFAULT_CONTAINER) -> bool:
        """Can this build do ``feature`` for ``container``?

        Consults the gate table first and falls back to the shim's own
        ``supports`` verb. The table is empty today, so every question still
        reaches the shim -- which is the point: the fallback is what makes
        populating the table a per-row change rather than a flag day.

        ``container`` is accepted and not yet used. The shim has nowhere to
        put it; widening the signature now means the tests that will need to
        ask a per-container question do not have to change again when an
        adapter can answer one.
        """
        result = self.gate_result(feature)
        if result is not None:
            logger.debug("sup %s %s -> %s (%s)", self, feature, bool(result), result.reason)
            return bool(result)
        argv, _ = self.supports_command(feature)
        logger.info("sup [%s]", " ".join(argv))
        try:
            subprocess.check_call(argv)
        except subprocess.CalledProcessError:
            return False
        return True

    def gate_result(self, feature: str) -> GateResult | None:
        """The table's verdict for ``feature``, or ``None`` if it has no entry."""
        gate = lookup(self.name, feature)
        if gate is None:
            return None
        return evaluate(gate, self, feature)

    # -- GateContext ------------------------------------------------------

    def version(self) -> SdkVersion:
        """What this build reports about itself.

        Memoized: java pays 150-500 ms of JVM startup per probe, which is why
        its shim grew a help-output cache in the first place.
        """
        if self._version is None:
            self._version = self._read_version()
        return self._version

    def help_text(self, *subcommand: str) -> str:
        """Help output for ``subcommand``, or ``""`` if it cannot be read."""
        if subcommand not in self._help:
            self._help[subcommand] = self._capture([self.path, "help", *subcommand])
        return self._help[subcommand]

    def ask_native(self, feature: str) -> bool:
        argv, _ = self.supports_command(feature)
        try:
            subprocess.check_call(argv)
        except (OSError, subprocess.CalledProcessError):
            return False
        return True

    # -- internals --------------------------------------------------------

    def _read_version(self) -> SdkVersion:
        raw = self._capture([self.path, "--version", "--json"]).strip()
        if not raw:
            return SdkVersion(raw="")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return SdkVersion(raw=raw)
        if not isinstance(data, dict):
            return SdkVersion(raw=raw)
        features = data.get("supported_features")
        return SdkVersion(
            raw=raw,
            # Three SDKs, three keys for the same fact. Reading all three here
            # costs nothing and saves a per-adapter override until the native
            # adapters exist to hold one.
            sdk=_first_str(data, "sdk_version", "version", "@opentdf/sdk"),
            schema=_first_str(data, "schema_version", "tdfSpecVersion"),
            features=tuple(str(f) for f in features) if isinstance(features, list) else (),
        )

    def _capture(self, argv: list[str]) -> str:
        try:
            result = subprocess.run(argv, capture_output=True, check=False)
        except OSError as e:
            logger.debug("probe failed: %s: %s", " ".join(argv), e)
            return ""
        return result.stdout.decode(errors="replace")

    def _run(self, argv: list[str], overrides: Mapping[str, str], *, label: str) -> None:
        env = dict(os.environ)
        env |= overrides
        result = subprocess.run(argv, env=env, capture_output=True, check=False)
        if result.returncode != 0:
            if result.stdout:
                logger.error("%s stdout: %s", label, result.stdout.decode(errors="replace"))
            if result.stderr:
                logger.error("%s stderr: %s", label, result.stderr.decode(errors="replace"))
            raise subprocess.CalledProcessError(
                result.returncode, argv, output=result.stdout, stderr=result.stderr
            )


def _first_str(data: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def fmt_env(env: Mapping[str, str]) -> str:
    """Render env overrides the way a shell would accept them, for logs."""
    return " ".join(f"{k}='{v}'" for k, v in env.items())


def adapter_for(
    name: str, version: str = "main", dist_dir: Path | None = None
) -> SubprocessCliAdapter:
    """Construct the shim adapter. The entry-point factory signature."""
    try:
        return SubprocessCliAdapter(name, version, dist_dir)
    except FileNotFoundError as e:
        raise AdapterError(str(e)) from e
