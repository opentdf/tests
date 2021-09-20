"""Authority Namespace Service SQLite."""

import logging
from typing import List, Optional

from ..errors import NotImplementedException
from ..models.authority_namespace import AuthorityNamespace

logger = logging.getLogger(__name__)


class AbstractAuthorityNamespaceService:
    """Authority Namespace Services data connector."""

    def create(self, body: dict) -> dict:
        """Create a new Authority Namespace.
        Return the request body if the operation was successful, otherwise
        raise an error.
        """
        raise NotImplementedException

    def retrieve(self, isDefault: bool = False, namespace: str = None) -> List[str]:
        """Retrieve all Authority Namespaces for this EAS."""
        raise NotImplementedException

    def get(self, namespace: str) -> Optional[AuthorityNamespace]:
        """Get one Authority NamespaceS."""
        raise NotImplementedException
