"""The Policy model."""

import base64
import json

import logging

from tdf3_kas_core.errors import PolicyError
from tdf3_kas_core.models import DataAttributes

from tdf3_kas_core.models.dissem import Dissem

logger = logging.getLogger(__name__)


def is_string(data):
    """Determine if data is string."""
    return isinstance(data, str)


class Policy(object):
    """This Policy model represents the policy.

    The Policy model is basically a container for smaller models. By design,
    it doesn't do much on its own.  The sub models hold most of the business
    logic. The Policy job is to hold those models together.
    """

    @classmethod
    def construct_from_raw_canonical(cls, canonical):
        """Build a policy object up from the raw canonical form.

        The canonical raw form is a base64 encoded version of the policy,
        encoded as string in json form. A copy of this canonical string is
        preserved as is for use in hmac validation.  Note that this string
        is not to be trusted as a representation of the policy as changes
        may occur in the attribute list and/or the dissem list.
        """
        raw_policy = json.JSONDecoder().decode(
            bytes.decode(base64.b64decode(str.encode(canonical)))
        )

        if is_string(raw_policy):  # special case for remote types
            policy = cls(raw_policy, canonical)

        else:  # all other types
            # Construct an "empty" policy object
            if "uuid" not in raw_policy:
                raise PolicyError("PolicyError: Polices must have uuids")

            uuid = raw_policy["uuid"]
            if not isinstance(uuid, str):
                raise PolicyError("PolicyError: UUID is not a string")

            # Construct the base policy
            policy = cls(uuid, canonical)

            # Load the body data
            if "body" in raw_policy:
                body = raw_policy["body"]
                if "dataAttributes" in body:
                    data_attrs = body["dataAttributes"]
                    logger.debug("Data attributes = %s", data_attrs)
                    policy.data_attributes.load_raw(data_attrs)
                if "dissem" in raw_policy["body"]:
                    dissem = body["dissem"]
                    logger.debug("Dissem = %s", dissem)
                    policy.dissem.list = dissem

        return policy

    def __init__(self, uuid, canonical=None):
        """Construct with uuid and cannonical form (binary).

        The constructor constructs only an empty policy object. Use the factory
        methods to both construct and load a policy.

        Note that the canonical string, if provided, is not to be trusted as
        a representation of the policy as the data attribute list and/or the
        dissem list may change.  Even if no additions or subractions occur the
        order of the attributes and the dissem entries is not guranteed.  Use
        the export_canonical() method to get a snapshot of the policy in
        canonical form.
        """
        logger.debug("---- Constructing Policy ---")
        logger.debug("uuid = %s", uuid)
        logger.debug("canonical = %s", canonical)

        self.__uuid = uuid
        self.__canonical = canonical
        self.__data_attributes = DataAttributes()
        self.__dissem = Dissem()

    def export_raw(self):
        """Produce a dict like the raw dict.

        Order not preserved in either the dissem or attribute lists.
        """
        dict = {
            "uuid": self.uuid,
            "body": {
                "dataAttributes": self.data_attributes.export_raw(),
                "dissem": self.dissem.list,
            },
        }
        logger.debug("Exporting raw dict = %s", dict)
        return dict

    @property
    def canonical(self):
        """Return the canonical form.

        Note that in python strings are immutable. Although this passes
        the canonical form by reference it is not possible for the external
        code to change the string that the reference points to so giving out
        the string directly is a safe thing to do.

        (This string ought to be depricated. It is used in an HMAC check that
        verifies that the object key and original policy have not been
        tampered with, however this check does not verify that THIS instance
        has not been tampered with.  The check is therefore valid only for
        verifying that the object key has not been altered, which is a bit
        misleading. I do not have a proposal for how to fix this - Tim)
        """
        return self.__canonical

    @canonical.setter
    def canonical(self, args):
        """Prevent the reference canonical form from changing."""
        pass

    def export_canonical(self):
        """Compute a canonical for the current state of the policy."""
        raw = self.export_raw()
        canonical = bytes.decode(base64.b64encode(str.encode(json.dumps(raw))))
        logger.debug("Exporting canonical = %s", canonical)
        return canonical

    @property
    def uuid(self):
        """Return the UUID.

        Note that in python strings are immutable. Although this passes
        the canonical form by reference it is not possible for the external
        code to change the string that the reference points to so giving out
        the string directly is a safe thing to do.
        """
        return self.__uuid

    @uuid.setter
    def uuid(self, new_uuid):
        """Prevent the uuid from changing."""
        pass

    @property
    def data_attributes(self):
        """Produce the data attributes model.

        The basic idea here is that the model can take care of itself.
        Instead of guarding the internal copy closely, produce it and let
        the policy plugin work with it directly.
        """
        return self.__data_attributes

    @data_attributes.setter
    def data_attributes(self, new_attributes):
        """Replace the DataAttributes model with another one."""
        if isinstance(new_attributes, DataAttributes):
            self.__data_attributes = new_attributes

    @property
    def dissem(self):
        """Produce the dissem model.

        The basic idea here is that the model can take care of itself.
        Instead of guarding the internal copy closely, produce it and let
        the policy plugin work with it directly.
        """
        return self.__dissem

    @dissem.setter
    def dissem(self, new_dissem):
        """Replace the Dissem model with another one."""
        if isinstance(new_dissem, Dissem):
            self.__dissem = new_dissem
