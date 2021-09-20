"""RSA encrypt/decrypt algorithms with SHA1 hashes."""

import logging

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from tdf3_kas_core.errors import CryptoError

from tdf3_kas_core.util import assure_public_key
from tdf3_kas_core.util import assure_private_key

logger = logging.getLogger(__name__)


def aes_encrypt_sha1(binary, public_key):
    """Encrypt AES using OAEP padding with SHA1 hash."""
    try:
        key = assure_public_key(public_key)
        return key.encrypt(
            binary,
            padding.OAEP(
                # TODO: https://virtru.atlassian.net/browse/PLAT-230
                # The following is not used in any security context.
                mgf=padding.MGF1(algorithm=hashes.SHA1()),  # nosec (B303)
                algorithm=hashes.SHA1(),  # nosec (B303)
                label=None,
            ),
        )
    except Exception as e:
        raise CryptoError("Encrypt failed") from e


def aes_decrypt_sha1(cipher, private_key):
    """Decrypt AES, given OAEP padding with SHA1 hash."""
    try:
        key = assure_private_key(private_key)
        return key.decrypt(
            cipher,
            padding.OAEP(
                # TODO: https://virtru.atlassian.net/browse/PLAT-230
                # The following is not used in any security context.
                mgf=padding.MGF1(algorithm=hashes.SHA1()),  # nosec (B303)
                algorithm=hashes.SHA1(),  # nosec (B303)
                label=None,
            ),
        )
    except Exception as e:
        raise CryptoError("Decrypt failed") from e
