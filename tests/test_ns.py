"""命名空间与工艺链拓扑。"""

from __future__ import annotations

import pytest

from hydrorefuel.errors import NamespaceError
from hydrorefuel.ns.registry import NamespaceRegistry
from hydrorefuel.ns.topology import build_default_topology


def test_registry_registers_and_resolves():
    registry = NamespaceRegistry("station1")
    device = registry.register("station", "vent", "vent-valve")
    assert device.address == "station.vent"
    assert registry.resolve("station.vent").kind == "vent-valve"
    assert registry.addresses() == ["station.vent"]
    assert registry.describe()["count"] == 1


def test_duplicate_and_unknown_addresses_are_rejected():
    registry = NamespaceRegistry()
    registry.register("station", "vent", "vent-valve")
    with pytest.raises(NamespaceError):
        registry.register("station", "vent", "vent-valve")
    with pytest.raises(NamespaceError):
        registry.resolve("station.missing")


def test_topology_requires_predecessors():
    topology = build_default_topology()
    assert topology.order()[0] == "unload"
    assert topology.predecessors("fill") == ("precool",)
    report = topology.verify(set())
    assert report["missing"]["pressurize"] == ["unload"]
    assert topology.verify({"unload"})["missing"].get("pressurize") is None
    assert topology.stage("audit").label == "审计"
    assert topology.summary()["order"] == topology.order()
