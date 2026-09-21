"""km3's generated KAS config, pinned against the km3 step in CI.

The KAO-URI tests run against a km3 started two different ways: by the
`start-additional-kas` action in `.github/workflows/xtest.yml`, and by
`otdf-local up` on a developer machine. Nothing but these tests connects the
two, so a setting added to one side stays absent from the other until some
test fails in CI and passes locally (or the reverse) for reasons that look
nothing like a config drift. Reading the workflow here is deliberate: a
hand-copied table of expected values would drift in exactly the same way.
"""

from pathlib import Path
from typing import Any

import pytest
from otdf_local.config.features import PlatformFeatures
from otdf_local.config.settings import Settings
from otdf_local.services.kas import KASService
from otdf_local.utils.yaml import get_nested, load_yaml, save_yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/xtest.yml"

ROOT_KEY = "0123456789abcdef0123456789abcdef"

#: A build new enough that no feature gate in `_generate_config` trims anything.
MODERN_PLATFORM = PlatformFeatures(
    version="99.0.0", semver=(99, 0, 0), features={"logger_stderr"}
)

#: Inputs on the CI km3 step, and the config key otdf-local must set for each.
#: Anything here is a setting both sides control; the tests below check that they
#: agree on it.
CI_INPUT_TO_CONFIG_KEY = {
    "ec-tdf-enabled": "services.kas.preview.ec_tdf_enabled",
    "key-management": "services.kas.preview.key_management",
    "pqc-enabled": "services.kas.preview.hybrid_tdf_enabled",
    "kas-uri-from-kao": "services.kas.kas_uri_from_kao",
    "key-cache-expiration": "services.kas.key_cache_expiration",
    "kas-port": "server.port",
    "log-level": "logger.level",
    "log-type": "logger.type",
    "root-key": "services.kas.root_key",
}

#: Inputs with nothing for otdf-local to match: ``kas-name`` names the instance
#: rather than configuring it, and the DPoP nonce tests are CI-only.
CI_INPUTS_WITHOUT_CONFIG_KEY = {"kas-name", "dpop-challenge-enabled"}

#: Inputs CI supplies as a version-gated expression rather than a literal. There is
#: no value to compare against, so these are checked for being enabled instead --
#: otdf-local targets a current platform and has no gate to mirror.
CI_EXPRESSION_INPUTS = {"key-management", "pqc-enabled"}


def _km3_step_inputs() -> dict[str, Any]:
    """The `with:` block of the km3 step in the X-Test workflow."""
    workflow = load_yaml(WORKFLOW)
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if step.get("id") == "kas-km3":
                return dict(step["with"])
    raise AssertionError(f"no step with `id: kas-km3` in {WORKFLOW}")


def _ci_value(ci_input: str) -> Any:
    """One input's value, with a readable failure if CI stopped passing it.

    Bare subscripting would raise a KeyError here, which reads as a broken test rather
    than as the drift these tests exist to report.
    """
    inputs = _km3_step_inputs()
    assert ci_input in inputs, f"the km3 CI step no longer passes {ci_input}"
    return inputs[ci_input]


def _is_expression(value: Any) -> bool:
    return isinstance(value, str) and "${{" in value


def _same_scalar(ci: Any, local: Any) -> bool:
    """Compare a workflow input to a config value across YAML's scalar types.

    The action takes every input as a string, so CI writes `true` where the config
    wants a bool and quotes `'300000000000'` where it wants an int. Comparing the
    rendered text is what the action itself effectively does.
    """
    return str(ci).strip().lower() == str(local).strip().lower()


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """A Settings pointing at a throwaway platform dir with the files KAS reads."""
    platform_dir = tmp_path / "platform"
    platform_dir.mkdir()
    save_yaml(
        platform_dir / "opentdf-dev.yaml", {"services": {"kas": {"root_key": ROOT_KEY}}}
    )
    save_yaml(
        platform_dir / "opentdf-kas-mode.yaml",
        {
            "logger": {"level": "info"},
            "server": {"port": 8080},
            "services": {"kas": {}},
        },
    )

    # PlatformFeatures.detect shells out to `go run ./service version`, which needs a
    # real platform checkout and a Go toolchain. Feature detection is not what these
    # tests are about, so pin it to a build that has everything.
    monkeypatch.setattr(
        PlatformFeatures, "detect", classmethod(lambda *_args: MODERN_PLATFORM)
    )

    settings = Settings(xtest_root=tmp_path, platform_dir=platform_dir)
    settings.ensure_directories()
    return settings


def _generated(settings: Settings, kas_name: str) -> dict[str, Any]:
    return load_yaml(KASService(settings, kas_name)._generate_config())  # noqa: SLF001


def test_every_ci_input_is_accounted_for() -> None:
    """A new input on the km3 step has to be classified before the rest can pass.

    Without this the parity tests only cover the inputs someone remembered to list,
    so adding a setting to CI and forgetting otdf-local would stay green.
    """
    assert set(_km3_step_inputs()) == set(CI_INPUT_TO_CONFIG_KEY) | (
        CI_INPUTS_WITHOUT_CONFIG_KEY
    )


def test_km3_config_sets_everything_the_ci_step_sets(settings: Settings) -> None:
    config = _generated(settings, "km3")
    missing = [
        key
        for key in CI_INPUT_TO_CONFIG_KEY.values()
        if get_nested(config, key) is None
    ]
    assert not missing, (
        f"the km3 CI step sets these; the generated config does not: {missing}"
    )


@pytest.mark.parametrize(
    "ci_input",
    sorted(set(CI_INPUT_TO_CONFIG_KEY) - CI_EXPRESSION_INPUTS - {"root-key"}),
)
def test_km3_config_matches_the_literal_ci_values(
    settings: Settings, ci_input: str
) -> None:
    ci_value = _ci_value(ci_input)
    assert not _is_expression(ci_value), (
        f"{ci_input} became an expression in CI; move it to CI_EXPRESSION_INPUTS"
    )
    local = get_nested(_generated(settings, "km3"), CI_INPUT_TO_CONFIG_KEY[ci_input])
    assert _same_scalar(ci_value, local), (
        f"{ci_input}: CI sets {ci_value!r}, otdf-local generates {local!r}"
    )


@pytest.mark.parametrize("ci_input", sorted(CI_EXPRESSION_INPUTS))
def test_version_gated_ci_inputs_are_enabled_locally(
    settings: Settings, ci_input: str
) -> None:
    """CI gates these on a platform-version check; otdf-local just turns them on."""
    assert _is_expression(_ci_value(ci_input)), (
        f"{ci_input} is now a literal in CI; drop it from CI_EXPRESSION_INPUTS so its "
        "value gets compared"
    )
    key = CI_INPUT_TO_CONFIG_KEY[ci_input]
    assert get_nested(_generated(settings, "km3"), key) is True


def test_km3_root_key_comes_from_the_platform_config(settings: Settings) -> None:
    """CI passes the platform's root key through; locally it is read off disk.

    Same requirement either way -- a km3 with its own root key cannot unwrap anything
    the platform wrapped -- but only this side can be checked against a known value.
    """
    assert get_nested(_generated(settings, "km3"), "services.kas.root_key") == ROOT_KEY


@pytest.mark.parametrize("kas_name", ["km1", "km2"])
def test_the_negative_control_kas_leave_kao_lookup_off(
    settings: Settings, kas_name: str
) -> None:
    """km1/km2 must not pick up km3's settings, or the negative test proves nothing.

    `test_decrypt_rejects_kao_kas_registration_when_disabled` asserts a KAO naming a
    URI other than the KAS's own `registered_kas_uri` fails to resolve. Enable
    kas_uri_from_kao on these and it passes for the wrong reason.
    """
    config = _generated(settings, kas_name)
    assert not get_nested(config, "services.kas.kas_uri_from_kao", False)
    assert get_nested(config, "services.kas.key_cache_expiration") is None
