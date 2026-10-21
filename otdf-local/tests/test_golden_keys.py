"""Tests that the golden keys legacy TDFs need reach the platform config.

`extra-keys.json` was looked up at `xtest_root / "xtest"`, a directory that
does not exist, so golden keys were silently never configured locally. Behind
that, `validate_kid` rejected `golden-r1` for its hyphen.
"""

import json
import shutil
import stat
from pathlib import Path

import pytest
from otdf_local.config.settings import Settings
from otdf_local.services.platform import PlatformService
from otdf_local.utils.keys import setup_golden_keys, validate_kid
from otdf_local.utils.yaml import get_nested, load_yaml

# The real fixture, so a rename or move in xtest/ breaks this test too.
EXTRA_KEYS = Path(__file__).resolve().parents[2] / "xtest" / "extra-keys.json"

# The key layout of the platform's committed opentdf-dev.yaml, trimmed.
TEMPLATE = """\
server:
  cryptoProvider:
    standard:
      keys:
      - kid: r1
        alg: rsa:2048
        private: kas-private.pem
        cert: kas-cert.pem
      - kid: e1
        alg: ec:secp256r1
        private: kas-ec-private.pem
        cert: kas-ec-cert.pem
services:
  kas:
    root_key: 00112233445566778899aabbccddeeff
    keyring:
    - kid: e1
      alg: ec:secp256r1
    - kid: r1
      alg: rsa:2048
"""

# As the manual fallback in otdf-local/CLAUDE.md leaves the template.
TEMPLATE_WITH_GOLDEN_KEY = """\
server:
  cryptoProvider:
    standard:
      keys:
      - kid: golden-r1
        alg: rsa:2048
        private: golden-r1-private.pem
        cert: golden-r1-cert.pem
services:
  kas:
    root_key: 00112233445566778899aabbccddeeff
    keyring:
    - kid: golden-r1
      alg: rsa:2048
      legacy: true
"""


@pytest.fixture
def xtest_root(tmp_path: Path) -> Path:
    root = tmp_path / "xtest"
    root.mkdir()
    shutil.copyfile(EXTRA_KEYS, root / "extra-keys.json")
    return root


@pytest.fixture
def platform_dir(tmp_path: Path) -> Path:
    platform_dir = tmp_path / "platform"
    platform_dir.mkdir()
    return platform_dir


def _platform(xtest_root: Path, platform_dir: Path, template: str) -> PlatformService:
    settings = Settings(xtest_root=xtest_root, platform_dir=platform_dir)
    settings.ensure_directories()
    settings.platform_template_config.write_text(template)
    return PlatformService(settings)


def _kids(data: dict, path: str) -> list[str]:
    return [entry["kid"] for entry in get_nested(data, path)]


def test_reads_extra_keys_from_the_xtest_directory(
    xtest_root: Path, platform_dir: Path
):
    keys = setup_golden_keys(xtest_root, platform_dir)

    assert [k["kid"] for k in keys] == ["golden-r1"]
    assert (platform_dir / "golden-r1-private.pem").is_file()
    assert (platform_dir / "golden-r1-cert.pem").is_file()


def test_the_private_key_is_owner_only(xtest_root: Path, platform_dir: Path):
    # Rewriting a key that an earlier run left world-readable narrows it too.
    private = platform_dir / "golden-r1-private.pem"
    private.write_text("stale")
    private.chmod(0o644)

    setup_golden_keys(xtest_root, platform_dir)

    assert stat.S_IMODE(private.stat().st_mode) == 0o600


def test_the_golden_key_is_added_alongside_the_existing_keys(
    xtest_root: Path, platform_dir: Path
):
    # Replacing the lists instead would drop r1/e1, and every TDF but the
    # golden ones would fail to decrypt.
    platform = _platform(xtest_root, platform_dir, TEMPLATE)

    data = load_yaml(platform._generate_config())

    assert _kids(data, "server.cryptoProvider.standard.keys") == [
        "r1",
        "e1",
        "golden-r1",
    ]
    assert _kids(data, "services.kas.keyring") == ["e1", "r1", "golden-r1"]


def test_a_golden_key_already_in_the_template_is_not_duplicated(
    xtest_root: Path, platform_dir: Path
):
    platform = _platform(xtest_root, platform_dir, TEMPLATE_WITH_GOLDEN_KEY)

    data = load_yaml(platform._generate_config())

    assert _kids(data, "server.cryptoProvider.standard.keys") == ["golden-r1"]
    assert _kids(data, "services.kas.keyring") == ["golden-r1"]


def test_a_missing_extra_keys_file_is_reported(
    tmp_path: Path, platform_dir: Path, capsys
):
    assert setup_golden_keys(tmp_path, platform_dir) == []
    # rich wraps to the terminal width
    out = " ".join(capsys.readouterr().out.split())
    assert "golden keys not configured" in out


def _golden_entry(**overrides) -> dict:
    return {**json.loads(EXTRA_KEYS.read_text())[0], **overrides}


@pytest.mark.parametrize(
    "content",
    [
        pytest.param("not json", id="not-json"),
        pytest.param(json.dumps({"kid": "golden-r1"}), id="object-not-array"),
        pytest.param(json.dumps(["golden-r1"]), id="entry-not-object"),
        pytest.param(json.dumps([_golden_entry(kid=1)]), id="kid-not-string"),
        pytest.param(json.dumps([_golden_entry(kid=None)]), id="kid-null"),
        pytest.param(json.dumps([_golden_entry(cert="")]), id="empty-cert"),
        pytest.param(json.dumps([_golden_entry(alg="rsa:1024")]), id="bad-alg"),
        pytest.param(
            json.dumps([_golden_entry(), _golden_entry(kid="Golden-R1")]),
            id="kids-collide-ignoring-case",
        ),
    ],
)
def test_a_malformed_extra_keys_file_is_a_value_error(
    content: str, xtest_root: Path, platform_dir: Path
):
    # ValueError is what PlatformService._preflight turns into start_error;
    # anything else escapes it as a traceback.
    (xtest_root / "extra-keys.json").write_text(content)

    with pytest.raises(ValueError, match="extra-keys.json"):
        setup_golden_keys(xtest_root, platform_dir)

    assert list(platform_dir.iterdir()) == []


def test_extra_keys_that_are_not_utf8_name_the_file(
    xtest_root: Path, platform_dir: Path
):
    # UnicodeDecodeError is already a ValueError, but its message does not
    # say which file it was decoding.
    (xtest_root / "extra-keys.json").write_bytes(b'[{"kid": "\xff"}]')

    with pytest.raises(ValueError, match="extra-keys.json"):
        setup_golden_keys(xtest_root, platform_dir)


def test_a_malformed_extra_keys_file_fails_start(xtest_root: Path, platform_dir: Path):
    (xtest_root / "extra-keys.json").write_text(json.dumps([_golden_entry(kid=1)]))
    platform = _platform(xtest_root, platform_dir, TEMPLATE)

    assert platform._preflight() is False
    assert platform.start_error is not None
    assert "extra-keys.json" in platform.start_error


@pytest.mark.parametrize("kid", ["golden-r1", "r1", "e1_x", "a" * 32])
def test_accepts_kids_in_use(kid: str):
    assert validate_kid(kid)


@pytest.mark.parametrize(
    "kid", ["", "a" * 33, "../evil", "a/b", "a.b", "-r1", "golden r1"]
)
def test_rejects_kids_that_are_not_safe_file_names(kid: str):
    assert not validate_kid(kid)
