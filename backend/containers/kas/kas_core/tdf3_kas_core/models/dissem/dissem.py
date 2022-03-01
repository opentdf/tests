"""The Dissem model."""

import logging
from json import JSONEncoder, JSONDecoder

logger = logging.getLogger(__name__)


class Dissem(object):
    """Container for a list of dissemination emails.

    Uniqueness is guaranteed, but order is not.
    """

    @classmethod
    def from_iterable(cls, iterable):
        """Create a Dissem instance from a list or set."""
        dissem = cls()
        # Use the setter to preserve any value checks.
        dissem.list = iterable
        return dissem

    @classmethod
    def from_json(cls, raw_json):
        """Create a new dissem model from a json string."""
        return cls.from_iterable(JSONDecoder().decode(raw_json))

    def __init__(self):
        """Create an empty Dissem model."""
        self.__set = set()

    @property
    def list(self):
        """Get the elements as a list.

        Order is not preserved.
        """
        return list(self.__set)

    @list.setter
    def list(self, new_list):
        """Set the element.

        Pack the list elements into a set, automatically removing duplicates.
        """
        self.__set.clear()
        for email in new_list:
            # use the email setter to check for validity
            self.add(email)

    def contains(self, email):
        """Check to see if dissem contains an email."""
        return email in self.__set

    @property
    def size(self):
        """Return the number of emails in the dissem set."""
        return len(self.__set)

    def clear(self):
        """Empty the dissem set."""
        self.__set.clear()

    def add(self, email):
        """Add an email.

        If it already exists then this is a noop.
        """
        self.__set.add(email)

    def remove(self, email):
        """Remove an email.

        If it doesn't exist then this is a noop.
        """
        self.__set.discard(email)

    def to_json(self):
        """Return a json-encoded list of the emails.

        Order is not preserved.
        """
        return JSONEncoder().encode(self.list)
