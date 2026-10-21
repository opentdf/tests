"""Tests for the generated platform and KAS configs.

Covers the preview flags and root key on the platform's built-in KAS, how a
generated root key is carried across regenerations, its propagation to
standalone KAS instances, failing before disturbing a running service when the
config is bad, and seeding of the pristine template.
"""

import re
from pathlib import Path

import subprocess

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

TEMPLATE_WITH_PREVIEW_DISABLED = """\
logger:
  level: info
services:
  kas:
    preview:
      ec_tdf_enabled: false
      hybrid_tdf_enabled: false
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
    @pytest.mark.parametrize(
        "template",
        [
            TEMPLATE_WITHOUT_ROOT_KEY,  # empty `preview` mapping
            TEMPLATE_WITH_ROOT_KEY,  # no `preview` key at all
            TEMPLATE_WITH_PREVIEW_DISABLED,  # explicitly off; still forced on
        ],
        ids=["empty-preview", "no-preview", "preview-disabled"],
    )
    def test_preview_features_are_enabled_on_the_default_kas(
        self, platform: PlatformService, template: str
    ):
        data = _generated_platform_config(platform, template)
        assert get_nested(data, "services.kas.preview.ec_tdf_enabled") is True
        assert get_nested(data, "services.kas.preview.hybrid_tdf_enabled") is True

    def test_log_level_is_debug(self, platform: PlatformService):
        # The OPENTDF_LOG_LEVEL env var never reached logger.level (see
        # PlatformService.start), so the generated config is the only place
        # the level is set.
        data = _generated_platform_config(platform, TEMPLATE_WITHOUT_ROOT_KEY)
        assert get_nested(data, "logger.level") == "debug"

    def test_missing_root_key_is_generated(self, platform: PlatformService):
        data = _generated_platform_config(platform, TEMPLATE_WITHOUT_ROOT_KEY)
        root_key = get_nested(data, "services.kas.root_key", "")
        assert re.fullmatch(r"[0-9a-f]{64}", root_key)

    def test_fresh_checkouts_get_different_root_keys(self, tmp_path: Path):
        keys = []
        for name in ("a", "b"):
            settings = Settings(xtest_root=tmp_path, platform_dir=tmp_path / name)
            settings.platform_dir.mkdir()
            settings.ensure_directories()
            data = _generated_platform_config(
                PlatformService(settings), TEMPLATE_WITHOUT_ROOT_KEY
            )
            keys.append(get_nested(data, "services.kas.root_key"))
        assert keys[0] != keys[1]

    def test_a_previous_config_without_a_key_gets_a_new_one(
        self, platform: PlatformService
    ):
        platform.settings.platform_config.write_text(TEMPLATE_WITHOUT_ROOT_KEY)
        data = _generated_platform_config(platform, TEMPLATE_WITHOUT_ROOT_KEY)
        assert re.fullmatch(
            r"[0-9a-f]{64}", get_nested(data, "services.kas.root_key", "")
        )

    def test_a_corrupt_previous_config_is_an_error_not_a_new_key(
        self, platform: PlatformService
    ):
        # Minting a fresh key here would silently rotate it under every
        # running KAS -- the failure carrying the key over exists to prevent.
        platform.settings.platform_config.write_text("services: [unclosed\n")
        platform.settings.platform_template_config.write_text(TEMPLATE_WITHOUT_ROOT_KEY)
        with pytest.raises(ValueError) as excinfo:
            platform._generate_config()
        assert str(platform.settings.platform_config) in str(excinfo.value)
        assert "root key" in str(excinfo.value)

    def test_a_pinned_root_key_is_left_alone(self, platform: PlatformService):
        data = _generated_platform_config(platform, TEMPLATE_WITH_ROOT_KEY)
        assert (
            get_nested(data, "services.kas.root_key")
            == "00112233445566778899aabbccddeeff"
        )

    def test_a_generated_root_key_survives_regeneration(
        self, platform: PlatformService
    ):
        # `restart platform` regenerates the config while KAS instances keep
        # running with the key they read at their own start.
        first = _generated_platform_config(platform, TEMPLATE_WITHOUT_ROOT_KEY)
        second = _generated_platform_config(platform, TEMPLATE_WITHOUT_ROOT_KEY)
        assert get_nested(first, "services.kas.root_key") == get_nested(
            second, "services.kas.root_key"
        )

    def test_a_pinned_root_key_replaces_a_generated_one(
        self, platform: PlatformService
    ):
        _generated_platform_config(platform, TEMPLATE_WITHOUT_ROOT_KEY)
        data = _generated_platform_config(platform, TEMPLATE_WITH_ROOT_KEY)
        assert (
            get_nested(data, "services.kas.root_key")
            == "00112233445566778899aabbccddeeff"
        )


class TestPristineTemplate:
    """Seeding `opentdf.yaml`, which an installed worktree lacks."""

    def test_an_installed_worktree_is_seeded_from_the_committed_config(
        self, platform: PlatformService
    ):
        platform.settings.platform_config.write_text(TEMPLATE_WITHOUT_ROOT_KEY)
        data = load_yaml(platform._generate_config())

        assert (
            platform.settings.platform_template_config.read_text()
            == TEMPLATE_WITHOUT_ROOT_KEY
        )
        assert get_nested(data, "services.kas.preview.ec_tdf_enabled") is True
        assert get_nested(data, "logger.level") == "debug"

    def test_the_template_is_not_reseeded_over(self, platform: PlatformService):
        platform.settings.platform_template_config.write_text(TEMPLATE_WITH_ROOT_KEY)
        platform.settings.platform_config.write_text(TEMPLATE_WITHOUT_ROOT_KEY)

        data = load_yaml(platform._generate_config())

        # An existing template is never overwritten by seeding.
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
        assert get_nested(template, "logger.level") == "info"

    def test_nothing_to_generate_from_says_so(self, platform: PlatformService):
        with pytest.raises(FileNotFoundError) as excinfo:
            platform._generate_config()
        assert "opentdf.yaml" in str(excinfo.value)
        assert "opentdf-dev.yaml" in str(excinfo.value)

    def test_seeding_takes_the_committed_config_not_an_earlier_run(
        self, platform: PlatformService
    ):
        # If opentdf.yaml was deleted after a run, opentdf-dev.yaml holds that
        # run's output; seeding from it would feed output back in as input.
        platform_dir = platform.settings.platform_dir
        config = platform.settings.platform_config
        config.write_text(TEMPLATE_WITHOUT_ROOT_KEY)
        git = [
            "git",
            "-C",
            str(platform_dir),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
        ]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "add", config.name], check=True)
        subprocess.run([*git, "commit", "-qm", "init"], check=True)
        config.write_text(TEMPLATE_WITH_ROOT_KEY)

        platform._generate_config()

        template = load_yaml(platform.settings.platform_template_config)
        assert get_nested(template, "services.kas.root_key") is None
        # The earlier run's key is still carried over into the generated
        # config, as for any key the template does not pin.
        generated = load_yaml(config)
        assert (
            get_nested(generated, "services.kas.root_key")
            == "00112233445566778899aabbccddeeff"
        )


class TestPlatformStart:
    @pytest.fixture
    def broken(self, platform: PlatformService, monkeypatch) -> list[str]:
        """A platform whose config cannot be generated; returns its kill log."""
        platform.settings.platform_config.write_text("services: [unclosed\n")
        platform.settings.platform_template_config.write_text(TEMPLATE_WITHOUT_ROOT_KEY)
        disturbed: list[str] = []
        monkeypatch.setattr(
            "otdf_local.services.platform.kill_process_on_port",
            lambda port: disturbed.append("kill"),
        )
        monkeypatch.setattr(platform, "stop", lambda: disturbed.append("stop"))
        return disturbed

    def test_start_reports_a_bad_config_without_killing_the_platform(
        self, platform: PlatformService, broken: list[str]
    ):
        assert platform.start() is False
        assert platform.start_error is not None
        assert str(platform.settings.platform_config) in platform.start_error
        assert broken == []

    def test_restart_with_a_bad_config_leaves_the_platform_running(
        self, platform: PlatformService, broken: list[str]
    ):
        assert platform.restart() is False
        assert platform.start_error is not None
        assert broken == []


class TestKASRootKey:
    @pytest.fixture
    def disturbed(self) -> list[str]:
        """Records each kill or stop of the KAS under test."""
        return []

    @pytest.fixture
    def kas(self, tmp_path: Path, monkeypatch, disturbed: list[str]) -> KASService:
        settings = Settings(xtest_root=tmp_path, platform_dir=tmp_path)
        settings.ensure_directories()
        settings.kas_template_config.write_text(KAS_TEMPLATE)
        monkeypatch.setattr(
            "otdf_local.services.kas.kill_process_on_port",
            lambda port: disturbed.append("kill"),
        )
        kas = KASService(settings, "alpha")
        monkeypatch.setattr(kas, "stop", lambda: disturbed.append("stop"))
        return kas

    def test_root_key_is_copied_from_the_platform_config(self, kas: KASService):
        kas.settings.platform_config.write_text(TEMPLATE_WITH_ROOT_KEY)

        data = load_yaml(kas._generate_config())

        assert (
            get_nested(data, "services.kas.root_key")
            == "00112233445566778899aabbccddeeff"
        )

    def test_an_absent_root_key_fails_loudly(self, kas: KASService):
        # See KASService._generate_config for why "" is not a usable default.
        kas.settings.platform_config.write_text(TEMPLATE_WITHOUT_ROOT_KEY)

        with pytest.raises(ValueError, match="root_key"):
            kas._generate_config()

    def test_start_reports_a_missing_root_key_as_a_start_error(
        self, kas: KASService, disturbed: list[str]
    ):
        # start() -> bool plus start_error is the contract of Service.start
        # that the CLI relies on; a raised exception would bypass its error
        # reporting.
        kas.settings.platform_config.write_text(TEMPLATE_WITHOUT_ROOT_KEY)

        assert kas.start() is False
        assert kas.start_error is not None
        assert "root_key" in kas.start_error
        assert disturbed == []

    def test_start_before_the_platform_says_to_start_it(
        self, kas: KASService, disturbed: list[str]
    ):
        assert kas.start() is False
        assert kas.start_error is not None
        assert str(kas.settings.platform_config) in kas.start_error
        assert "Start the platform first" in kas.start_error
        assert disturbed == []

    def test_a_corrupt_platform_config_is_a_start_error(
        self, kas: KASService, disturbed: list[str]
    ):
        kas.settings.platform_config.write_text("services: [unclosed\n")

        assert kas.start() is False
        assert kas.start_error is not None
        assert str(kas.settings.platform_config) in kas.start_error
        assert disturbed == []

    def test_restart_with_a_bad_config_leaves_the_kas_running(
        self, kas: KASService, disturbed: list[str]
    ):
        # Service.restart stops before it starts; the preflight must come
        # first or a bad config still takes the running KAS down.
        kas.settings.platform_config.write_text(TEMPLATE_WITHOUT_ROOT_KEY)

        assert kas.restart() is False
        assert kas.start_error is not None
        assert "root_key" in kas.start_error
        assert disturbed == []
