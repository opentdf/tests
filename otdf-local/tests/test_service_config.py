"""Tests for the generated platform config."""

from pathlib import Path

import pytest
from otdf_local.config.settings import Settings
from otdf_local.services.platform import PlatformService
from otdf_local.utils.yaml import get_nested, load_yaml

TEMPLATE_WITHOUT_ROOT_KEY = """\
logger:
  level: info
services:
  kas:
    preview: {}
"""

TEMPLATE_WITH_ROOT_KEY = """\
logger:
  level: info
services:
  kas:
    root_key: 00112233445566778899aabbccddeeff
"""


@pytest.fixture
def platform(tmp_path: Path) -> PlatformService:
    """A PlatformService whose config generation touches only `tmp_path`."""
    settings = Settings(xtest_root=tmp_path, platform_dir=tmp_path)
    settings.ensure_directories()
    # Golden keys come from xtest/extra-keys.json, which tmp_path lacks;
    # setup_golden_keys already returns [] for that, so config generation is
    # exercised end to end without needing the real fixture file.
    return PlatformService(settings)


class TestPristineTemplate:
    """Generation needs a pristine copy an installed worktree does not have.

    `opentdf.yaml` is gitignored in the platform repo and made by hand in the
    manual setup; `otdf-sdk-mgr install platform` does not make it. Since
    `opentdf-dev.yaml` is both the committed config and where generation
    *writes*, the seeding has to happen before the first write.
    """

    def test_an_installed_worktree_is_seeded_from_the_committed_config(
        self, platform: PlatformService
    ):
        platform.settings.platform_config.write_text(TEMPLATE_WITHOUT_ROOT_KEY)
        data = load_yaml(platform._generate_config())

        assert platform.settings.platform_template_config.is_file()
        assert get_nested(data, "logger.level") == "debug"

    def test_the_template_is_not_reseeded_over(self, platform: PlatformService):
        platform.settings.platform_template_config.write_text(TEMPLATE_WITH_ROOT_KEY)
        platform.settings.platform_config.write_text(TEMPLATE_WITHOUT_ROOT_KEY)

        data = load_yaml(platform._generate_config())

        # The hand-made template wins. Seeding from the generated file instead
        # would silently swap out the key golden-TDF fixtures are encrypted to.
        assert (
            get_nested(data, "services.kas.root_key")
            == "00112233445566778899aabbccddeeff"
        )

    def test_generating_does_not_fold_output_back_into_the_template(
        self, platform: PlatformService
    ):
        platform.settings.platform_config.write_text(TEMPLATE_WITHOUT_ROOT_KEY)
        platform._generate_config()

        # Whatever generation changed -- the log level here, golden keyring
        # entries in a real checkout -- must not come back as next run's input,
        # or the appended sections accumulate a copy per run.
        template = load_yaml(platform.settings.platform_template_config)
        assert get_nested(template, "logger.level") == "info"

    def test_nothing_to_generate_from_says_so(self, platform: PlatformService):
        with pytest.raises(FileNotFoundError) as excinfo:
            platform._generate_config()
        assert "opentdf.yaml" in str(excinfo.value)
        assert "opentdf-dev.yaml" in str(excinfo.value)
