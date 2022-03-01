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
        # ClaimsAttributes class takes unpacks the raw data for each attribute
        claims_attributes = ClaimsAttributes.create_from_raw(
            claims_cert_obj["subject_attributes"]
        )
        # Pack and ship the instance
        return cls(user_id, claims_public_key, claims_attributes)

    def __init__(self, user_id, public_key, claims_attributes=None):
        """Initialize with verified data.

        user_id should be a string.
        claims_public_key should be a RSAPublicKey object
        claims_attributes should be an ClaimsAttributes object.
        """
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

        if claims_attributes is None:
            self._attributes = ClaimsAttributes()
        elif isinstance(claims_attributes, ClaimsAttributes):
            self._attributes = claims_attributes
        else:
            raise ClaimsError("claims_attributes is wrong type")

    @property
    def user_id(self):
        """Produce the user_id of the Claims."""
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
    def attributes(self):
        """Produce the claims attributes."""
        return self._attributes

    @attributes.setter
    def attributes(self, new_attributes):
        """Block intadvertent changes to the claims attributes."""
        pass
