"""The DSPX-5111 range server as a fixture, stopped when the test ends."""

from collections.abc import Callable, Iterator
from contextlib import ExitStack

import pytest

import rangeserve


@pytest.fixture
def range_server() -> Iterator[
    Callable[[rangeserve.Source], tuple[str, list[rangeserve.Request]]]
]:
    """Call with a source; returns ``(url, request_log)``. Any number per test."""
    with ExitStack() as stack:
        yield lambda source: stack.enter_context(rangeserve.serve(source))
