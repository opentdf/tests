"""Bounded streaming controls for each SDK CLI (DSPX-5108).

Opt-in: ``--stream chunky`` is the 5 MiB control, run on every PR;
``--stream medium`` the 2.1 GiB one, run nightly beside the ZIP64 tests.
Neither adds a size to the ``pt_file``/``--sizes`` fanout.

Each SDK is probed first, at 5 MiB, for which of a FIFO and a regular file its
CLI accepts as input and as output (see :func:`streamharness.probe`). The
probe's chosen encrypt and decrypt are the 5 MiB control; larger sizes reuse
the chosen routes. Either way the TDF's ZIP structure and manifest must account
for exactly the plaintext sent, the decrypted output must match the generator
byte for byte, and no step may hold three full copies in scratch.

Nothing here skips: a route a CLI cannot take is reported as unsupported, with
the reason, in the terminal and job summaries.
"""

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

import sizes
import streamharness as sh
import tdfs
from fixtures.streaming import (
    PROBE_BYTES,
    decrypt_command,
    encrypt_command,
    probe_notes,
    row,
    stream_scratch,
    summarize,
)

pytestmark = pytest.mark.stream


def test_stream_control(
    encrypt_sdk: tdfs.SDK,
    stream_size: str,
    stream_probe: Callable[[tdfs.SDK], sh.Probe],
    tmp_dir: Path,
    record_property: Callable[[str, object], None],
):
    sdk = encrypt_sdk
    probe = stream_probe(sdk)
    record_property("encrypt_route", str(probe.encrypt.route))
    record_property("decrypt_route", str(probe.decrypt.route))
    length = sizes.SIZES[stream_size]

    if length == PROBE_BYTES:
        enc, dec = probe.encrypt.run, probe.decrypt.run
        assert enc is not None and dec is not None
    else:
        scratch = stream_scratch(tmp_dir, sdk, stream_size)
        plaintext = sh.Plaintext(length)
        budget = sh.Budget.from_env(timeout_s=3600)
        ciphertext = scratch / "control.tdf"
        try:
            enc = sh.encrypt(
                encrypt_command(sdk),
                plaintext,
                route=probe.encrypt.route,
                scratch=scratch,
                budget=budget,
                downstream=sh.FileSink(ciphertext),
            )
            dec = sh.decrypt(
                decrypt_command(sdk),
                ciphertext,
                plaintext,
                length,
                route=probe.decrypt.route,
                scratch=scratch,
                budget=budget,
            )
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        summarize(
            f"{sdk}: {stream_size} control",
            [
                row("encrypt", probe.encrypt.route, "ok", enc),
                row("decrypt", probe.decrypt.route, "ok", dec),
            ],
            probe_notes(probe),
        )

    assert enc.bytes_in == length
    evidence = enc.result
    assert isinstance(evidence, sh.TdfEvidence)
    assert evidence.manifest.plaintext_length == length
    assert enc.bytes_out == evidence.byte_count
    assert dec.result == dec.bytes_out == length
    # Every copy is at least the plaintext's length, so three of anything reach
    # 3x. Below 5 MiB the TDF's own overhead outweighs the payload.
    peak = max(enc.peak_scratch_bytes, dec.peak_scratch_bytes)
    if length >= PROBE_BYTES:
        assert peak < 3 * length, (
            f"scratch peaked at {peak} bytes: three copies of {length}"
        )
