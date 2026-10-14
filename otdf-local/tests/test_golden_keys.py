"""Tests that the golden keys legacy TDFs need reach the platform config.

`extra-keys.json` was looked up at `xtest_root / "xtest"`, a directory that
does not exist, so golden keys were silently never configured locally. Behind
that, `validate_kid` rejected `golden-r1` for its hyphen.
"""

import shutil
from pathlib import Path

import pytest
from otdf_local.config.settings import Settings
from otdf_local.services.platform import PlatformService
from otdf_local.utils.keys import setup_golden_keys, validate_kid
from otdf_local.utils.yaml import get_nested, load_yaml

# The real fixture, so a rename or move in xtest/ breaks this test too.
EXTRA_KEYS = Path(__file__).resolve().parents[2] / "xtest" / "extra-keys.json"

TEMPLATE = """\
services:
  kas:
    root_key: 00112233445566778899aabbccddeeff
"""


@pytest.fixture
def xtest_root(tmp_path: Path) -> Path:
    root = tmp_path / "xtest"
    root.mkdir()
    shutil.copyfile(EXTRA_KEYS, root / "extra-keys.json")
    return root


def test_reads_extra_keys_from_the_xtest_directory(xtest_root: Path, tmp_path: Path):
    platform_dir = tmp_path / "platform"
    platform_dir.mkdir()

    keys = setup_golden_keys(xtest_root, platform_dir)

    assert [k["kid"] for k in keys] == ["golden-r1"]
    assert (platform_dir / "golden-r1-private.pem").is_file()
    assert (platform_dir / "golden-r1-cert.pem").is_file()


def test_generated_config_carries_the_golden_key(xtest_root: Path, tmp_path: Path):
    platform_dir = tmp_path / "platform"
    platform_dir.mkdir()
    settings = Settings(xtest_root=xtest_root, platform_dir=platform_dir)
    settings.ensure_directories()
    settings.platform_template_config.write_text(TEMPLATE)
    platform = PlatformService(settings)

    platform._generate_config()
    data = load_yaml(platform._generate_config())

    # Once each, however many times the config is regenerated.
    keys = get_nested(data, "server.cryptoProvider.standard.keys")
    keyring = get_nested(data, "services.kas.keyring")
    assert [k["kid"] for k in keys] == ["golden-r1"]
    assert [k["kid"] for k in keyring] == ["golden-r1"]


@pytest.mark.parametrize("kid", ["golden-r1", "r1", "e1_x", "a" * 32])
def test_accepts_kids_in_use(kid: str):
    assert validate_kid(kid)


@pytest.mark.parametrize(
    "kid", ["", "a" * 33, "../evil", "a/b", "a.b", "-r1", "golden r1"]
)
def test_rejects_kids_that_are_not_safe_file_names(kid: str):
    assert not validate_kid(kid)
