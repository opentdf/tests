"""Unit checks for the IdP provider configs and the overlay renderer.

No platform or IdP is needed: these validate the YAML files under
idp/providers/, the platform-config fragments rendered from them, and the
environment the harness derives for each provider.
"""

from pathlib import Path

import pytest
import yaml

from fixtures.obligations import (
    DEFAULT_SUBJECT_SELECTOR,
    DEFAULT_SUBJECT_VALUES,
    subject_condition_from_env,
)
from idp import platform_config
from idp.provider import IdpProvider, list_providers, load_provider

pytestmark = pytest.mark.no_audit_logs


def _provider(name: str) -> IdpProvider:
    return load_provider(name).provider


@pytest.mark.parametrize("name", list_providers())
def test_every_provider_config_validates(name: str) -> None:
    resolved = load_provider(name)
    assert resolved.provider.name == name
    # External providers may be missing secrets locally; that is a skip
    # condition at runtime, not a schema error.
    assert resolved.provider.tier in ("local", "external", "self-hosted")


def test_keycloak_is_the_jwt_reference_provider() -> None:
    kc = _provider("keycloak")
    assert kc.tier == "local"
    assert kc.token_format == "jwt"
    assert kc.platform.repo == "opentdf/platform"
    assert kc.sdks == []
    assert kc.subject_condition.selector == DEFAULT_SUBJECT_SELECTOR
    assert kc.subject_condition.values == DEFAULT_SUBJECT_VALUES


def test_defaults_match_keycloak_conventions() -> None:
    """Providers that say nothing get Keycloak's subject condition, so
    existing provider files keep their behaviour."""
    minimal = IdpProvider(
        name="minimal",
        issuer="https://idp.example",
        audience="http://localhost:8080",
        client_id="c",
        client_secret="s",
    )
    assert minimal.token_format == "jwt"
    assert minimal.subject_condition.selector == ".clientId"
    assert minimal.subject_condition.values == DEFAULT_SUBJECT_VALUES
    assert minimal.platform.repo == "opentdf/platform"
    assert minimal.service is None


def test_authnz_rs_is_a_self_hosted_cwt_provider() -> None:
    p = _provider("authnz-rs")
    assert p.tier == "self-hosted"
    assert p.token_format == "cwt"
    assert p.service is not None
    assert p.service.repo == "arkavo-org/authnz-rs"
    assert p.platform.repo == "arkavo-org/opentdf-platform"
    assert p.sdks == ["rust", "swift"]
    assert p.ers.mode == "claims"
    assert p.subject_condition.selector == ".sub"
    assert p.subject_condition.values == ["client:opentdf"]
    assert p.token_endpoint == "http://localhost:8899/oauth/token"
    assert p.platform_overlay.casbin_groups_claim == "arkavo_roles"
    assert p.platform_overlay.casbin_extension is not None
    assert "role:admin" in p.platform_overlay.casbin_extension


def test_overlay_fragment_contains_only_provider_keys() -> None:
    frag = platform_config.overlay_fragment(_provider("authnz-rs"))
    assert set(frag) == {"server", "services"}
    auth = frag["server"]["auth"]
    assert auth["issuer"] == "http://localhost:8899"
    assert auth["audience"] == "http://localhost:8080"
    assert auth["dpop"] == {"enforce": False}
    assert auth["policy"]["groups_claim"] == "arkavo_roles"
    assert "g, service-account, role:admin" in auth["policy"]["extension"]
    assert frag["services"] == {"entityresolution": {"mode": "claims"}}


def test_render_overlay_merges_into_base(tmp_path: Path) -> None:
    base = tmp_path / "base.yaml"
    base.write_text(
        yaml.safe_dump(
            {
                "server": {
                    "port": 8080,
                    "auth": {
                        "enabled": True,
                        "issuer": "http://localhost:8888/auth/realms/opentdf",
                        "policy": {"username_claim": "preferred_username"},
                    },
                },
                "services": {"kas": {"root_key": "abc"}},
            }
        )
    )
    config = platform_config.render_overlay("authnz-rs", base)
    # Untouched base keys survive.
    assert config["server"]["port"] == 8080
    assert config["server"]["auth"]["enabled"] is True
    assert config["server"]["auth"]["policy"]["username_claim"] == "preferred_username"
    assert config["services"]["kas"] == {"root_key": "abc"}
    # Overlay keys win.
    assert config["server"]["auth"]["issuer"] == "http://localhost:8899"
    assert config["server"]["auth"]["policy"]["groups_claim"] == "arkavo_roles"
    assert config["services"]["entityresolution"]["mode"] == "claims"


def test_fragment_mode_writes_yaml(tmp_path: Path) -> None:
    out = tmp_path / "fragment.yaml"
    assert platform_config.main(["authnz-rs", "--fragment", str(out)]) == 0
    loaded = yaml.safe_load(out.read_text())
    assert loaded == platform_config.overlay_fragment(_provider("authnz-rs"))


def test_harness_env_for_authnz_rs() -> None:
    env = platform_config.harness_env(_provider("authnz-rs"))
    assert env == {
        "CLIENTID": "opentdf",
        "CLIENTSECRET": "secret",
        "XT_SUBJECT_SELECTOR": ".sub",
        "XT_SUBJECT_VALUES": "client:opentdf",
        "TOKENENDPOINT": "http://localhost:8899/oauth/token",
    }


def test_harness_env_omits_token_endpoint_when_discovered() -> None:
    env = platform_config.harness_env(_provider("keycloak"))
    assert "TOKENENDPOINT" not in env
    assert env["XT_SUBJECT_SELECTOR"] == ".clientId"
    assert env["XT_SUBJECT_VALUES"] == "opentdf,opentdf-sdk,opentdf-dpop"


def test_env_mode_prints_shell_exports(capsys: pytest.CaptureFixture[str]) -> None:
    assert platform_config.main(["authnz-rs", "--env"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "export XT_SUBJECT_SELECTOR=.sub" in lines
    assert "export XT_SUBJECT_VALUES=client:opentdf" in lines
    assert "export TOKENENDPOINT=http://localhost:8899/oauth/token" in lines


def test_subject_condition_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XT_SUBJECT_SELECTOR", raising=False)
    monkeypatch.delenv("XT_SUBJECT_VALUES", raising=False)
    assert subject_condition_from_env() == (
        DEFAULT_SUBJECT_SELECTOR,
        DEFAULT_SUBJECT_VALUES,
    )


def test_subject_condition_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XT_SUBJECT_SELECTOR", ".sub")
    monkeypatch.setenv("XT_SUBJECT_VALUES", "client:opentdf, client:other,")
    assert subject_condition_from_env() == (".sub", ["client:opentdf", "client:other"])


def test_subject_condition_env_blank_means_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XT_SUBJECT_SELECTOR", "  ")
    monkeypatch.setenv("XT_SUBJECT_VALUES", ",")
    assert subject_condition_from_env() == (
        DEFAULT_SUBJECT_SELECTOR,
        DEFAULT_SUBJECT_VALUES,
    )
