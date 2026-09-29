"""Tests for the generated platform and KAS configs.

A benchmark run starts the default KAS on its own -- no km1/km2, so no
background Go processes competing for CPU with the thing being timed. That
shape used to lose two settings that were only ever written onto the km
instances, and it lost them quietly: the affected cells skipped and the run
still reported success. These tests pin the settings to the platform config,
where every KAS reads them from.
"""

from pathlib import Path

import pytest
from otdf_local.config.settings import Settings
from otdf_local.services.kas import KASService
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

KAS_TEMPLATE = """\
logger:
  level: info
server:
  port: 8080
services:
  kas: {}
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


def _generated_platform_config(platform: PlatformService, template: str) -> dict:
    platform.settings.platform_template_config.write_text(template)
    return load_yaml(platform._generate_config())


class TestPlatformConfig:
    def test_preview_features_are_enabled_on_the_default_kas(
        self, platform: PlatformService
    ):
        data = _generated_platform_config(platform, TEMPLATE_WITHOUT_ROOT_KEY)
        assert get_nested(data, "services.kas.preview.ec_tdf_enabled") is True
        assert get_nested(data, "services.kas.preview.hybrid_tdf_enabled") is True

    def test_missing_root_key_is_generated(self, platform: PlatformService):
        data = _generated_platform_config(platform, TEMPLATE_WITHOUT_ROOT_KEY)
        root_key = get_nested(data, "services.kas.root_key", "")
        # 256 bits of hex; the point is that it is present and not a placeholder.
        assert len(root_key) == 64
        assert int(root_key, 16) >= 0

    def test_a_pinned_root_key_is_left_alone(self, platform: PlatformService):
        # Golden-TDF fixtures are encrypted against the template's key, so
        # replacing it would break test_legacy.py rather than fix anything.
        data = _generated_platform_config(platform, TEMPLATE_WITH_ROOT_KEY)
        assert (
            get_nested(data, "services.kas.root_key")
            == "00112233445566778899aabbccddeeff"
        )

    def test_generated_root_keys_differ_between_runs(self, platform: PlatformService):
        first = _generated_platform_config(platform, TEMPLATE_WITHOUT_ROOT_KEY)
        second = _generated_platform_config(platform, TEMPLATE_WITHOUT_ROOT_KEY)
        assert get_nested(first, "services.kas.root_key") != get_nested(
            second, "services.kas.root_key"
        )


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
        assert get_nested(data, "services.kas.preview.ec_tdf_enabled") is True

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

        # Whatever generation added -- a root key here, golden keyring entries
        # in a real checkout -- must not come back as next run's input, or the
        # appended sections accumulate a copy per run.
        template = load_yaml(platform.settings.platform_template_config)
        assert not get_nested(template, "services.kas.root_key", "")

    def test_nothing_to_generate_from_says_so(self, platform: PlatformService):
        with pytest.raises(FileNotFoundError) as excinfo:
            platform._generate_config()
        assert "opentdf.yaml" in str(excinfo.value)
        assert "opentdf-dev.yaml" in str(excinfo.value)


class TestKASRootKey:
    def _kas(self, tmp_path: Path, monkeypatch) -> KASService:
        settings = Settings(xtest_root=tmp_path, platform_dir=tmp_path)
        settings.ensure_directories()
        settings.kas_template_config.write_text(KAS_TEMPLATE)
        monkeypatch.setattr(
            "otdf_local.services.kas.kill_process_on_port", lambda port: None
        )
        return KASService(settings, "alpha")

    def test_root_key_is_copied_from_the_platform_config(self, tmp_path, monkeypatch):
        kas = self._kas(tmp_path, monkeypatch)
        kas.settings.platform_config.write_text(TEMPLATE_WITH_ROOT_KEY)

        data = load_yaml(kas._generate_config())

        assert (
            get_nested(data, "services.kas.root_key")
            == "00112233445566778899aabbccddeeff"
        )

    def test_an_absent_root_key_fails_loudly(self, tmp_path, monkeypatch):
        # Silently configuring root_key: "" yields a KAS that unwraps nothing
        # and only says so as "cipher: message authentication failed" minutes
        # later, from the SDK, with no mention of the config.
        kas = self._kas(tmp_path, monkeypatch)
        kas.settings.platform_config.write_text(TEMPLATE_WITHOUT_ROOT_KEY)

        with pytest.raises(ValueError, match="root_key"):
            kas._generate_config()

    def test_start_reports_a_missing_root_key_as_a_start_error(
        self, tmp_path, monkeypatch
    ):
        # start() -> bool plus start_error is the contract every caller in
        # cli.py uses; a raised exception would bypass all of them.
        kas = self._kas(tmp_path, monkeypatch)
        kas.settings.platform_config.write_text(TEMPLATE_WITHOUT_ROOT_KEY)

        assert kas.start() is False
        assert kas.start_error is not None
        assert "root_key" in kas.start_error
