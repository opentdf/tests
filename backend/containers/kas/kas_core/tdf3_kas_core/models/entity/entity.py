"""The entity object represents the entity asking for the rewrap."""
import logging

import logging

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey

from tdf3_kas_core.authorized import unpack_rs256_jwt
from tdf3_kas_core.models import EntityAttributes
from tdf3_kas_core.models import ClaimsAttributes
from tdf3_kas_core.errors import AuthorizationError
from tdf3_kas_core.errors import EntityError

logger = logging.getLogger(__name__)


class Entity(object):
    """Entity models the requesting entity.

    This may be the user's browser client, a service in a cloud, or
    some other software acting on behalf of a user entity.
    """

    @classmethod
    def load_from_raw_data(cls, raw_data, aa_public_key):
        """Create an Entity object from raw data.

        The raw data is trusted if it checks out with the AA public key.
        """
        # Ensure the cert is valid
        try:
            entity_cert_obj = unpack_rs256_jwt(raw_data["cert"], aa_public_key)

        except Exception as e:
            logger.setLevel(logging.DEBUG)  # dynamically escalate level
            raise AuthorizationError("Cert not valid") from e

        # Unpack the raw data
        user_id = entity_cert_obj["userId"]
        # The public key is packaged in the cert string
        entity_public_key = serialization.load_pem_public_key(
            str.encode(entity_cert_obj["publicKey"]), backend=default_backend()
        )
        # EntityAttributes class takes unpacks the raw data for each attribute
        entity_attributes = EntityAttributes.create_from_raw(
            entity_cert_obj["attributes"], aa_public_key
        )
        # Pack and ship the instance
        return cls(user_id, entity_public_key, entity_attributes)

    def __init__(self, user_id, public_key, entity_attributes=None):
        """Initialize with verified data.

        user_id should be a string.
        entity_public_key should be a RSAPublicKey object
        entity_attributes should be an EntityAttributes object.
        """
        if isinstance(user_id, str):
            self._user_id = user_id
        else:
            raise EntityError("user_id must be a string")

        if isinstance(public_key, RSAPublicKey):
            self._public_key = public_key
        elif isinstance(public_key, EllipticCurvePublicKey):
            self._public_key = public_key
        else:
            raise EntityError("public_key is wrong type")

        if entity_attributes is None:
            self._attributes = EntityAttributes()
        elif isinstance(entity_attributes, EntityAttributes):
            self._attributes = entity_attributes
        elif isinstance(entity_attributes, ClaimsAttributes):
            self._attributes = entity_attributes
        else:
            raise EntityError("entity_attributes is wrong type")

    @property
    def user_id(self):
        """Produce the user_id of the Entity."""
        return self._user_id

    @user_id.setter
    def user_id(self, new_id):
        """Block inadvertent changes to the user_id."""
        pass

    @property
    def public_key(self):
        """Produce the entity public key."""
        return self._public_key

    @public_key.setter
    def public_key(self, new_key):
        """Block inadvertent changes to the entity public key."""
        pass

    @property
    def attributes(self):
        """Produce the entity attributes."""
        return self._attributes

    @attributes.setter
    def attributes(self, new_attributes):
        """Block intadvertent changes to the entity attributes."""
        pass
