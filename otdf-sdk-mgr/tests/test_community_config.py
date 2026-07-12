"""Community SDK registration must not pollute official ALL_SDKS defaults."""

from otdf_sdk_mgr.config import (
    ALL_SDKS,
    COMMUNITY_SDKS,
    KNOWN_SDKS,
    SDK_BARE_REPOS,
    SDK_GIT_URLS,
    get_sdk_dirs,
)


def test_all_sdks_official_only():
    assert ALL_SDKS == ["go", "js", "java"]
    assert "python" not in ALL_SDKS
    assert "rust" not in ALL_SDKS
    assert "swift" not in ALL_SDKS


def test_community_sdks_registered():
    assert COMMUNITY_SDKS == ["rust", "swift", "python"]
    assert set(KNOWN_SDKS) == set(ALL_SDKS + COMMUNITY_SDKS)


def test_community_git_urls():
    for sdk in COMMUNITY_SDKS:
        assert sdk in SDK_GIT_URLS
        assert SDK_GIT_URLS[sdk].startswith("https://")
        assert sdk in SDK_BARE_REPOS


def test_get_sdk_dirs_includes_community(monkeypatch, tmp_path):
    monkeypatch.setenv("OTDF_SDK_DIR", str(tmp_path))
    dirs = get_sdk_dirs()
    for name in ALL_SDKS + COMMUNITY_SDKS:
        assert name in dirs
        assert dirs[name] == tmp_path / name
