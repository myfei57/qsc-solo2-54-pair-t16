"""平台装配、控制周期与并发探测。"""

from __future__ import annotations


def test_cycle_reports_state(platform):
    platform.start()
    first = platform.cycle()
    second = platform.cycle()
    assert first["cycle"] == 1
    assert second["cycle"] == 2
    assert "buffer_pressure_mpa" in second
    assert "leak_tripped" in second


def test_snapshot_contains_all_components(platform):
    platform.start()
    snapshot = platform.snapshot()
    for key in ("status", "topology", "namespaces", "trend", "readiness"):
        assert key in snapshot
    for key in ("truck", "vent", "compressor", "buffer", "cool", "flow", "disp", "leak", "queue"):
        assert key in snapshot["status"]


def test_concurrency_probe_converges(platform):
    platform.start()
    probe = platform.concurrency_probe(rounds=12)
    assert probe["setpoint"]["contenders"] == 2
    assert probe["confirm_attempts"] == 2
    assert probe["confirm_accepted"] == 1
    assert probe["committed_mpa"] == probe["setpoint"]["value_mpa"]


def test_namespace_resolution(platform):
    assert platform.namespace("station.vent")["kind"] == "vent-valve"
    assert platform.namespaces_describe()["count"] == 10


def test_reset_state_clears_counts(platform):
    platform.start()
    platform.cycle()
    result = platform.reset_state()
    assert result["platform_state_removed"] is True
    assert platform.status()["cycles"] == 0
