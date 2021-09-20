import logging
from enum import Enum

logger = logging.getLogger(__name__)


class State(Enum):
    """State class is used to indicate whether other objects are active or inactive

    this supports "soft delete".
    IMPORTANT only add to the end of the ENUM, the index is stored in the DB"""

    ACTIVE = 1
    INACTIVE = 2

    @staticmethod
    def from_input(s):
        """Take numeric, string, or enum input and return State enum"""
        if isinstance(s, int):
            return State(s)
        if isinstance(s, str):
            return State[s.upper()]
        if isinstance(s, State):
            return s
        logger.warning("%s is not a valid State", s)
        return None

    def to_string(self) -> str:
        if not self:
            # Edge case to support JSONEncoder use of State.to_string()
            return ""
        return self.name.lower()
