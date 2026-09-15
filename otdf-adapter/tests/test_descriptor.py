"""Reading an install's descriptor, and the shim layout it has to coexist with."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from otdf_adapter.descriptor import AdapterDescriptor, DescriptorError


def write(dist: Path, payload: object) -> Path:
    dist.mkdir(parents=True, exist_ok=True)
    path = dist / "adapter.json"
    path.write_text(json.dumps(payload) if not isinstance(payload, str) else payload)
    return path


class TestLoad:
    def test_a_missing_descriptor_falls_back_to_the_shim(self, tmp_path: Path):
        # Every build installed to date. Not an error, and must not be: the
        # descriptor is written by an installer change that has not landed.
        d = AdapterDescriptor.load(tmp_path, sdk="go", version="main")
        assert d.adapter == "go"
        assert d.exec == (str(tmp_path / "cli.sh"),)

    def test_a_descriptor_replaces_the_runtime_derivation(self, tmp_path: Path):
        # The three-branch `.version` parse that both shims re-run on every
        # invocation collapses into a value someone already computed.
        write(
            tmp_path,
            {
                "sdk": "go",
                "version": "v0.31.0",
                "adapter": "go",
                "exec": ["go", "run", "example.invalid/otdfctl@v0.31.0"],
            },
        )
        d = AdapterDescriptor.load(tmp_path)
        assert d.version == "v0.31.0"
        assert d.exec == ("go", "run", "example.invalid/otdfctl@v0.31.0")

    def test_adapter_defaults_to_the_sdk_name(self, tmp_path: Path):
        write(tmp_path, {"sdk": "js", "version": "main", "exec": ["npx", "ctl"]})
        assert AdapterDescriptor.load(tmp_path).adapter == "js"

    @pytest.mark.parametrize(
        "payload",
        [
            "not json at all",
            json.dumps([1, 2]),
            json.dumps({"sdk": "go"}),
            json.dumps({"sdk": "go", "exec": []}),
            json.dumps({"sdk": "go", "exec": "go run x"}),
            json.dumps({"sdk": "go", "exec": ["go", 7]}),
        ],
    )
    def test_a_malformed_descriptor_raises_rather_than_falling_back(
        self, tmp_path: Path, payload: str
    ):
        # Falling back would run a different build than the caller asked for
        # and report the result under the requested version's name, which is
        # the one failure mode a cross-version matrix cannot survive.
        write(tmp_path, payload)
        with pytest.raises(DescriptorError):
            AdapterDescriptor.load(tmp_path, sdk="go", version="v1.2.3")


class TestRoundTrip:
    def test_to_json_is_loadable(self, tmp_path: Path):
        original = AdapterDescriptor(
            sdk="java", version="v0.18.0", adapter="java", exec=("java", "-jar", "x.jar")
        )
        (tmp_path / "adapter.json").write_text(original.to_json())
        loaded = AdapterDescriptor.load(tmp_path)
        assert (loaded.sdk, loaded.version, loaded.adapter, loaded.exec) == (
            original.sdk,
            original.version,
            original.adapter,
            original.exec,
        )
