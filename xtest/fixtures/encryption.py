"""Session-scoped factory fixture for memoized TDF encryption.

The cache key and filenames are derived automatically from the test name and input.
"""

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

import tdfs

EncryptFactory = Callable[..., Path]


@pytest.fixture(scope="session")
def _encryption_cache() -> dict[tuple, Path]:
    """Session-wide cache mapping input-tuple keys to encrypted Paths."""
    return {}


@pytest.fixture
def encrypted_tdf(
    request: pytest.FixtureRequest,
    pt_file: Path,
    tmp_dir: Path,
    _encryption_cache: dict[tuple, Path],
) -> EncryptFactory:
    """Return a memoized encrypt-to-TDF function.

    Two callers that pass identical inputs share a ciphertext; differing
    inputs produce distinct ciphertexts. The on-disk filename embeds the
    requesting test's name plus a short hash for debuggability.
    """
    label = request.node.originalname or request.node.name

    def _factory(
        encrypt_sdk: tdfs.SDK,
        *,
        container: tdfs.container_type = "ztdf",
        attr_values: list[str] | None = None,
        target_mode: tdfs.container_version | None = None,
        az: str = "",
        mime_type: str = "text/plain",
    ) -> Path:
        attr_key = tuple(attr_values) if attr_values is not None else None
        key = (str(encrypt_sdk), container, target_mode, attr_key, az, mime_type)
        cached = _encryption_cache.get(key)
        if cached is not None:
            return cached
        digest = hashlib.sha1(repr(key).encode()).hexdigest()[:8]
        ct_file = tmp_dir / f"ct-{label}-{encrypt_sdk}-{container}-{digest}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            mime_type=mime_type,
            container=container,
            attr_values=attr_values,
            assert_value=az,
            target_mode=target_mode,
        )
        assert ct_file.is_file()
        _encryption_cache[key] = ct_file
        return ct_file

    return _factory
