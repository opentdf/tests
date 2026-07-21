"""Smoke tests for the multi-instance refactor.

These tests exercise the path resolution and port arithmetic without
requiring a real platform build or running services. The goal is to catch
regressions in the wiring between `otdf-sdk-mgr.schema`, `Settings`, and the
service launchers.
"""

from __future__ import annotations

from pathlib import Path

from otdf_sdk_mgr.schema import (
    Instance,
    KasPin,
    Metadata,
    PlatformPin,
    PortsConfig,
    dump_instance,
)

from otdf_local.config.ports import Ports
from otdf_local.config.settings import Settings


def test_ports_offset_layout_at_default_base() -> None:
    assert Ports.platform_port_for(8080) == 8080
    assert Ports.get_kas_port("alpha", base=8080) == 8181
    assert Ports.get_kas_port("km2", base=8080) == 8686


def test_ports_offset_layout_at_alternate_base() -> None:
    assert Ports.platform_port_for(9080) == 9080
    assert Ports.get_kas_port("alpha", base=9080) == 9181
    assert Ports.get_kas_port("km1", base=9080) == 9585


def test_settings_default_has_no_instance(tmp_path: Path) -> None:
    fake_xtest = tmp_path / "xtest"
    fake_xtest.mkdir()
    s = Settings(xtest_root=fake_xtest, platform_dir=None)
    assert s.instance_name == "default"
    assert not s.has_instance()


def test_settings_loads_instance_when_present(tmp_path: Path) -> None:
    fake_xtest = tmp_path / "xtest"
    fake_xtest.mkdir()
    instances_root = tmp_path / "instances"
    instance_dir = instances_root / "demo"
    instance_dir.mkdir(parents=True)
    dump_instance(
        Instance(
            metadata=Metadata(name="demo"),
            platform=PlatformPin(dist="v0.9.0"),
            ports=PortsConfig(base=9080),
            kas={"alpha": KasPin(dist="v0.9.0", mode="standard")},
        ),
        instance_dir / "instance.yaml",
    )
    s = Settings(xtest_root=fake_xtest, platform_dir=None, instance_name="demo")
    assert s.has_instance()
    inst = s.load_instance()
    assert inst is not None
    assert inst.ports.base == 9080
    # Per-instance port arithmetic
    assert s.get_kas_port("alpha") == 9181
    # Per-instance directory layout
    assert s.logs_dir == instance_dir / "logs"
    assert s.keys_dir == instance_dir / "keys"
