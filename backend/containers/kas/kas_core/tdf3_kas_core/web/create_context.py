"""Create the context object."""

import logging

from tdf3_kas_core.models import Context

logger = logging.getLogger(__name__)


def create_context(headers):
    """Process headers and other data into the context object."""
    context = Context()
    for (key, value) in headers.items():
        # keys may repeat with additional values. Context accumulates
        # these in list values under the same key.
        context.add(key, value)

    return context
