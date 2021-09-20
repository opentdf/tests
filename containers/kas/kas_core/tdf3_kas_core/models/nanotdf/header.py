from .constants import MAGIC_STRING
from .locator import ResourceLocator
from .eccbinding import ECCMode
from .symconfig import SymmetricAndPayloadConfig
from .policy import Policy
from .data import ByteData


class Header(object):
    def __init__(
        self,
        kas: ResourceLocator,
        ecc_mode: ECCMode,
        symmetric_and_payload_config: SymmetricAndPayloadConfig,
        policy: Policy,
        key: ByteData,
    ):
        self._kas = kas
        self._ecc_mode = ecc_mode
        self._symmetric_and_payload_config = symmetric_and_payload_config
        self._policy = policy
        self._key = key

    @property
    def kas(self) -> ResourceLocator:
        return self._kas

    @property
    def ecc_mode(self) -> ECCMode:
        return self._ecc_mode

    @property
    def symmetric_and_payload_config(self) -> SymmetricAndPayloadConfig:
        return self._symmetric_and_payload_config

    @property
    def policy(self) -> Policy:
        return self._policy

    @property
    def key(self) -> ByteData:
        return self._key

    @property
    def magic_number_and_version(self) -> bytes:
        return MAGIC_STRING

    def serialize(self) -> bytes:
        return b"%s%s%s%s%s%s" % (
            MAGIC_STRING,
            self.kas.serialize(),
            self.ecc_mode.serialize(),
            self.symmetric_and_payload_config.serialize(),
            self.policy.serialize(),
            self.key.serialize(),
        )
