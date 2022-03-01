"""The context model represents /rewrap context."""

import copy
import logging

from collections.abc import Sequence
from requests.structures import CaseInsensitiveDict

logger = logging.getLogger(__name__)


def is_seq(x):
    """Test to see if x is a sequence of discrete values.

    Exclude character and byte sequences.
    """
    return isinstance(x, Sequence) and not isinstance(x, str)


class Context(CaseInsensitiveDict):
    """Represents /rewrap service context.

    The context model captures web context data to hand off to the policy
    plugins.  It implements the builder pattern.

    The Context object is loosely based on the werkzeug Header object that
    Flask apps provide via Request objects. Why repeat the functionality
    here?  Because A) WSGI exceeds the requirement for the context object,
    and B) having a local Context class insulates the plugins from changes
    the werkzug library.
    """

    def add(self, key, value):
        """Set the value that goes with the key.

        The key may already have a value. If so, and the value is a scalar,
        this method replaces it with a list with the new value after the old
        value.  If the value is a sequence already then it extends the original
        list with the new value(s), i.e. it also flattens.
        """
        value = copy.deepcopy(value)
        if key not in self:
            if is_seq(value):
                value = list(value)
            self[key] = value
            return

        # convert existing value to a list if it isn't already.
        head = self[key]
        if not is_seq(head):
            head = [head]
        tail = value
        if not is_seq(tail):
            tail = [tail]
        self[key] = head + list(tail)

    def get(self, key):
        """Get the value that goes with the key, if any."""
        if not key in self:
            return None
        return copy.deepcopy(self[key])

    def has(self, key):
        """Check if key exists."""
        return key in self

    @property
    def size(self):
        """Return the number of keys in .__data."""
        return len(self)

    @property
    def data(self):
        """Provide a deep copies of the data via .get method."""
        obj = CaseInsensitiveDict()
        for key in self.keys():
            # Use the explicit get method to get the immutable list variant
            obj[key] = self.get(key)
        return obj

    @data.setter
    def data(self, new_data):
        """Noop to protect .__data."""
        # should this throw an error?
        pass
