"""Session-scoped factory fixture for memoized TDF encryption.

The cache key is derived from encryption input parameters; on-disk filenames also embed
the requesting test's name and a short hash for debuggability.
"""

import hashlib
from pathlib import Path

import pytest

import tdfs


class EncryptFactory:
    """Memoized TDF encryption factory bound to the current test.

    Call to encrypt (results are cached by input parameters). Use rt_file() to
    generate a test-unique decrypted output path derived from the ciphertext.
    """

    def __init__(
        self,
        label: str,
        pt_file: Path,
        tmp_dir: Path,
        cache: dict[tuple, Path],
    ) -> None:
        self._label = label
        self._pt_file = pt_file
        self._tmp_dir = tmp_dir
        self._cache = cache

    def __call__(
        self,
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
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        digest = hashlib.sha1(repr(key).encode()).hexdigest()[:8]
        ct_file = self._tmp_dir / f"ct-{self._label}-{encrypt_sdk}-{container}-{digest}.tdf"
        encrypt_sdk.encrypt(
            self._pt_file,
            ct_file,
            mime_type=mime_type,
            container=container,
            attr_values=attr_values,
            assert_value=az,
            target_mode=target_mode,
        )
        assert ct_file.is_file()
        self._cache[key] = ct_file
        return ct_file

    def rt_file(self, ct_file: Path, decrypt_sdk: tdfs.SDK, variant: str = "") -> Path:
        """Return a test-unique path for the decrypted output.

        Embeds the current test label so tests that share a cached ciphertext
        don't collide on their output files.
        """
        variant_part = f"-{variant}" if variant else ""
        return ct_file.with_name(
            f"{ct_file.stem}-{decrypt_sdk}-{self._label}{variant_part}.untdf"
        )


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
    """Return a memoized encrypt-to-TDF factory for the current test.

    Two callers with identical inputs share a ciphertext; differing inputs
    produce distinct ciphertexts. Use rt_file() to get a test-unique output path.
    """
    label = request.node.originalname or request.node.name
    return EncryptFactory(label, pt_file, tmp_dir, _encryption_cache)
