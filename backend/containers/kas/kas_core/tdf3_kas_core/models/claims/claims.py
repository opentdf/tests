"""The claims object represents the entity asking for the rewrap."""
import logging

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey

from tdf3_kas_core.models import ClaimsAttributes
from tdf3_kas_core.errors import AuthorizationError
from tdf3_kas_core.errors import ClaimsError

logger = logging.getLogger(__name__)


class Claims(object):
    """Claims models the requesting claims.

    This may be the user's browser client, a service in a cloud, or
    some other software acting on behalf of a user claims.
    """

    @classmethod
    def load_from_raw_data(cls, raw_data):
        """Create an Claims object from raw data."""
        claims_cert_obj = raw_data["tdf_claims"]

        # Unpack the raw data
        user_id = raw_data["sub"]

        # The public key is packaged in the cert string
        claims_public_key = serialization.load_pem_public_key(
            str.encode(claims_cert_obj["client_public_signing_key"]),
            backend=default_backend(),
        )

        # ClaimsAttributes class takes a list of entitlements, each with
        # an entity ID and list of entity attributes, and builds an object out of them
        # for Reasons and because We Need A Custom Object Model For Simple Types In Lists, apparently.
        # Why choose a language with a strict type system when you can choose a language with a loose type
        # system and write your own typing enforcement on top of that, I guess.

        entity_attributes = ClaimsAttributes.create_from_raw(
            claims_cert_obj["entitlements"]
        )
        # Pack and ship the instance
        return cls(user_id, claims_public_key, entity_attributes)

    def __init__(self, user_id, public_key, claims_entity_attributes=None):
        """Initialize with verified data.

        user_id should be a string.
        claims_public_key should be a RSAPublicKey object
        claims_entity_attributes should be a entity-ID-keyed dict of ClaimsAttributes objects.
        """

        # TODO WHY ARE WE WRITING OUR OWN TYPECHECKING LOGIC?
        # If we really need this typechecking, use a statically-typed language
        # Otherwise just embrace the fact that python is a dynamically-typed language and
        # stop rolling our own typing checks?!
        if isinstance(user_id, str):
            self._user_id = user_id
        else:
            raise ClaimsError("user_id must be a string")

        if isinstance(public_key, RSAPublicKey):
            self._client_public_signing_key = public_key
        elif isinstance(public_key, EllipticCurvePublicKey):
            self._client_public_signing_key = public_key
        else:
            raise ClaimsError("client_public_signing_key is wrong type")
        if claims_entity_attributes is None:
            self._attributes = {}
        elif isinstance(claims_entity_attributes, dict):
            self._entity_attributes = claims_entity_attributes
        else:
            raise ClaimsError("claims_entity_attributes is wrong type")

    @property
    def user_id(self):
        """Produce the user_name of the Claims, as reported by OIDC JWT 'preferred_username' property"""
        return self._user_id

    @user_id.setter
    def user_id(self, new_id):
        """Block inadvertent changes to the user_id."""
        pass

    @property
    def client_public_signing_key(self):
        """Produce the claims public key."""
        return self._client_public_signing_key

    @client_public_signing_key.setter
    def client_public_signing_key(self, new_key):
        """Block inadvertent changes to the claims public key."""
        pass

    @property
    def entity_attributes(self):
        """Produce the claims attributes."""
        return self._entity_attributes

    @entity_attributes.setter
    def entity_attributes(self, new_entity_attributes):
        # TODO what actual purpose does this serve, we're in a dynamically typed language
        """Block intadvertent changes to the claims attributes."""
        pass
